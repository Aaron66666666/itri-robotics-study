import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from ultralytics import YOLO


class YoloNode(Node):

    def __init__(self):
        super().__init__('yolo_node')

        # 建立 ROS 2 Publisher
        self.publisher_ = self.create_publisher(
            String,
            '/yolo/detections',
            10
        )

        # 載入 YOLO 模型
        model_path = '/home/yulin/yolo_project/yolo26n.pt'
        self.model = YOLO(model_path)

        # 設定要辨識的圖片
        self.image_path = '/home/yulin/yolo_project/images/test.jpg'

        # 建立計時器，每 2 秒執行一次辨識
        self.timer = self.create_timer(2.0, self.detect_objects)

        self.get_logger().info('YOLO ROS 2 節點已啟動！')

    def detect_objects(self):

        # 使用 YOLO 辨識圖片
        results = self.model.predict(
            source=self.image_path,
            device='cpu',
            conf=0.50,
            classes=[0],
            verbose=False
        )

        # 整理辨識結果
        detections = []

        for result in results:
            for box in result.boxes:

                class_id = int(box.cls[0])
                class_name = result.names[class_id]
                confidence = float(box.conf[0])

                x1, y1, x2, y2 = box.xyxy[0].tolist()

                detection = (
                    f'class={class_name}, '
                    f'confidence={confidence:.2%}, '
                    f'box=({x1:.1f}, {y1:.1f}, '
                    f'{x2:.1f}, {y2:.1f})'
                )

                detections.append(detection)

        # 將結果發布到 ROS 2 Topic
        message = String()

        if detections:
            message.data = '\n'.join(detections)
        else:
            message.data = '沒有偵測到人物'

        self.publisher_.publish(message)

        self.get_logger().info(
            f'已發布辨識結果，共偵測到 {len(detections)} 個人物'
        )


def main(args=None):

    rclpy.init(args=args)

    node = YoloNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
