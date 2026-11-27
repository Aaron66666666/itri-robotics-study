import json
import os
from pathlib import Path
import sys
import time

# ROS 2 generated console scripts use system Python. Add the existing YOLO
# virtual environment packages so this node can import both ROS and YOLO.
python_version = f'python{sys.version_info.major}.{sys.version_info.minor}'
yolo_venv = Path(
    os.environ.get('YOLO_VENV', str(Path.home() / 'yolo_project' / '.venv'))
)
yolo_site_packages = yolo_venv / 'lib' / python_version / 'site-packages'
if yolo_site_packages.is_dir():
    sys.path.insert(0, str(yolo_site_packages))

# YOLO weights by short name (yolo_model:=v3|v5|coco); model_path:=FILE
# overrides the name. Weights live in ~/yolo_project and are not in git.
#   v3    YOLO26n fine-tuned on Gazebo data (stage 2), the accepted default
#   v5    same recipe, images regenerated without the boxes Gazebo drew on them
#   coco  the original YOLO26n
MODEL_DIR = Path.home() / 'yolo_project'
YOLO_MODELS = {
    'v3': 'yolo26n_gazebo_v3.pt',
    'v5': 'yolo26n_gazebo_v5clean.pt',
    'coco': 'yolo26n.pt',
}
DEFAULT_YOLO_MODEL = 'v3'

import cv2  # noqa: E402
from cv_bridge import CvBridge  # noqa: E402
import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from rclpy.qos import qos_profile_sensor_data  # noqa: E402
from sensor_msgs.msg import Image  # noqa: E402
from std_msgs.msg import String  # noqa: E402
from ultralytics import YOLO  # noqa: E402


def resolve_model_path(yolo_model, model_path=''):
    """Return model_path if it is set, else the weights file of yolo_model."""
    if model_path:
        # '~' is not expanded by the shell in 'model_path:=~/...'.
        return os.path.expanduser(model_path)
    if yolo_model not in YOLO_MODELS:
        raise ValueError(
            f'unknown yolo_model {yolo_model!r}: use one of '
            f'{", ".join(YOLO_MODELS)}, or model_path:=FILE')
    return str(MODEL_DIR / YOLO_MODELS[yolo_model])


def save_diagnostic_frame(frame, image_path):
    """Save one lossless BGR frame without overwriting an existing file."""
    path = Path(image_path)
    if path.suffix.lower() != '.png':
        raise ValueError('diagnostic frame path must end in .png')
    success, encoded = cv2.imencode('.png', frame)
    if not success:
        raise RuntimeError('OpenCV could not encode the diagnostic frame')
    with path.open('xb') as output:
        output.write(encoded.tobytes())


class CameraSubscriber(Node):

    def __init__(self):
        super().__init__('camera_subscriber')

        self.declare_parameter(
            'image_topic', '/vehicle_blue/camera/image'
        )
        self.declare_parameter('yolo_model', DEFAULT_YOLO_MODEL)
        self.declare_parameter('model_path', '')
        self.declare_parameter('confidence_threshold', 0.35)
        self.declare_parameter('device', 'auto')
        self.declare_parameter('display', False)
        self.declare_parameter('diagnostic_frame_path', '')

        image_topic = self.get_parameter('image_topic').value
        yolo_model = self.get_parameter('yolo_model').value
        model_path = resolve_model_path(
            yolo_model, self.get_parameter('model_path').value)
        if not Path(model_path).is_file():
            # Never let Ultralytics fall back to downloading a model.
            raise FileNotFoundError(
                f'YOLO weights not found: {model_path} (see README, '
                '"YOLO 模型": copy or retrain the weights, or choose '
                'another model with yolo_model:=v3|v5|coco)')
        self.confidence_threshold = float(
            self.get_parameter('confidence_threshold').value
        )
        device = self.get_parameter('device').value
        self.device = None if device == 'auto' else device
        self.display = bool(self.get_parameter('display').value)
        self.diagnostic_frame_path = self.get_parameter(
            'diagnostic_frame_path'
        ).value
        self.diagnostic_frame_saved = False

        # ROS 2 影像轉換工具
        self.bridge = CvBridge()

        # 載入既有 YOLO 模型，不會下載或更動模型檔案。
        self.model = YOLO(model_path)

        # 計算 FPS
        self.last_time = time.time()
        self.fps = 0.0
        self.frame_count = 0
        self.inference_count = 0
        self.last_detection_signature = None

        # 發布結構化辨識結果與畫好辨識框的影像。
        self.detections_publisher = self.create_publisher(
            String,
            '/yolo/detections',
            10
        )
        self.image_publisher = self.create_publisher(
            Image,
            '/yolo/image',
            10
        )

        # 感測器影像採用 sensor-data QoS，讓訂閱端優先取得最新畫面。
        self.subscription = self.create_subscription(
            Image,
            image_topic,
            self.image_callback,
            qos_profile_sensor_data
        )

        self.get_logger().info(f'YOLO model loaded: {model_path}')
        self.get_logger().info(
            f'YOLO inference settings: conf={self.confidence_threshold}, '
            f'device={device}'
        )
        self.get_logger().info(f'Python executable: {sys.executable}')
        self.get_logger().info(
            f'YOLO Python packages: {yolo_site_packages}'
        )
        self.get_logger().info(f'Subscribing to camera: {image_topic}')
        self.get_logger().info('Publishing detections: /yolo/detections')
        self.get_logger().info('Publishing annotated image: /yolo/image')

    def image_callback(self, msg):

        # 將 ROS 2 影像訊息轉換成 OpenCV 影像
        try:
            frame = self.bridge.imgmsg_to_cv2(
                msg,
                desired_encoding='bgr8'
            )
        except Exception as e:
            self.get_logger().error(f'Image conversion failed: {e}')
            return

        self.frame_count += 1
        if self.frame_count == 1 or self.frame_count % 30 == 0:
            channel_means = frame.mean(axis=(0, 1)).round(2).tolist()
            self.get_logger().info(
                f'Received camera frame {self.frame_count}: '
                f'encoding={msg.encoding}, shape={frame.shape}, '
                f'dtype={frame.dtype}, channel_order=BGR, '
                f'min={frame.min()}, max={frame.max()}, '
                f'channel_means={channel_means}'
            )

        if self.diagnostic_frame_path and not self.diagnostic_frame_saved:
            try:
                save_diagnostic_frame(
                    frame, self.diagnostic_frame_path
                )
                self.diagnostic_frame_saved = True
                self.get_logger().info(
                    'Saved one lossless diagnostic camera frame: '
                    f'{self.diagnostic_frame_path}'
                )
            except Exception as e:
                self.diagnostic_frame_saved = True
                self.get_logger().error(
                    f'Diagnostic frame was not saved: {e}'
                )

        # 使用 YOLO 辨識影像中的物件
        try:
            inference_started = time.perf_counter()
            results = self.model.predict(
                source=frame,
                conf=self.confidence_threshold,
                device=self.device,
                verbose=False
            )
            inference_seconds = time.perf_counter() - inference_started

            # 將辨識框與標籤繪製到影像上
            result = results[0]
            annotated_frame = result.plot()

            detections = []
            if result.boxes is not None:
                for box in result.boxes:
                    class_id = int(box.cls[0].item())
                    confidence = float(box.conf[0].item())
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    detections.append({
                        'class_id': class_id,
                        'class_name': result.names[class_id],
                        'confidence': confidence,
                        'bbox_xyxy': [x1, y1, x2, y2],
                    })

            self.inference_count += 1
            detected = [
                    f'{item["class_name"]}:{item["confidence"]:.4f}'
                    for item in detections
            ]
            signature = tuple(detected)
            if (self.inference_count == 1
                    or self.inference_count % 30 == 0
                    or signature != self.last_detection_signature):
                predictor = getattr(self.model, 'predictor', None)
                runtime_device = getattr(predictor, 'device', 'unknown')
                self.get_logger().info(
                    f'YOLO inference {self.inference_count} complete; '
                    f'elapsed={inference_seconds:.3f}s, '
                    f'runtime_device={runtime_device}, '
                    f'detections={detected}'
                )
            self.last_detection_signature = signature

        except Exception as e:
            self.get_logger().error(
                f'YOLO detection failed on camera frame {self.frame_count}: {e}'
            )
            return

        # String 內使用 JSON，方便其他 ROS 節點解析類別、信心值與框座標。
        detection_message = String()
        detection_message.data = json.dumps({
            'stamp': {
                'sec': msg.header.stamp.sec,
                'nanosec': msg.header.stamp.nanosec,
            },
            'frame_id': msg.header.frame_id,
            'image_size': {
                'width': frame.shape[1],
                'height': frame.shape[0],
            },
            'detections': detections,
        }, ensure_ascii=False)
        self.detections_publisher.publish(detection_message)

        # 計算 FPS
        current_time = time.time()
        elapsed = current_time - self.last_time

        if elapsed > 0:
            self.fps = 1.0 / elapsed

        self.last_time = current_time

        # 在標註影像加上 FPS，並發布供其他 ROS 工具查看。
        cv2.putText(
            annotated_frame,
            f'FPS: {self.fps:.1f}',
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        annotated_message = self.bridge.cv2_to_imgmsg(
            annotated_frame,
            encoding='bgr8'
        )
        annotated_message.header = msg.header
        self.image_publisher.publish(annotated_message)

        # GUI 預設關閉；需要本機視窗時可用 display:=true 開啟。
        if self.display:
            cv2.imshow('Robot Camera - YOLO Detection', annotated_frame)
            cv2.waitKey(1)


def main(args=None):
    rclpy.init(args=args)

    node = None

    try:
        node = CameraSubscriber()
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    except Exception as e:
        print(f'Program error: {e}')

    finally:
        if node is not None:
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()

        if node is not None and node.display:
            cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
