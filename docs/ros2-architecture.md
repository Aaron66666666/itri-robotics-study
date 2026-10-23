# ROS 2 程式架構學習筆記

## 1. ROS 2 是什麼？

ROS 2 是機器人開發框架，提供節點、訊息傳遞、程式管理等功能，讓不同程式能夠互相合作。

## 2. Node（節點）

Node 是 ROS 2 中負責特定工作的程式。例如，控制車輛的程式是一個 Node，讀取車輛位置的程式則是另一個 Node。

## 3. Topic（主題）

Topic 是 ROS 2 節點之間傳遞資料的通道。節點可以透過 Topic 發送或接收訊息。

本次實作使用的 Topic：

- `/model/vehicle_blue/cmd_vel`：傳送藍色車輛的速度控制指令。
- `/model/vehicle_blue/odometry`：讀取藍色車輛的位置與運動資訊。

## 4. Publisher（發布者）

Publisher 負責向 Topic 發布訊息。

實際操作中，`move_robot.py` 會發布 `Twist` 訊息，控制車輛前進、轉彎或停止。

## 5. Subscriber（訂閱者）

Subscriber 負責接收 Topic 上的訊息。

實際操作中，`read_odom.py` 訂閱 Odometry Topic，持續讀取車輛的 X、Y 座標與前進速度。

## 6. Gazebo 與 ROS 2 Bridge

Gazebo 是機器人模擬器，可以模擬機器人、環境與物理運動。

ROS 2 Bridge 負責在 ROS 2 與 Gazebo Transport 之間轉換並傳遞訊息，讓 ROS 2 程式可以控制 Gazebo 中的車輛，並讀取模擬器提供的資料。

本次實作使用 `ros_gz_bridge`，連接車輛的速度控制與 Odometry 資訊。

## 7. 本次專案的資料流向

### 車輛控制

1. `move_robot.py` 發布 `Twist` 速度指令。
2. 指令透過 `/model/vehicle_blue/cmd_vel` 傳遞。
3. ROS 2 Bridge 將訊息轉換並傳送至 Gazebo。
4. Gazebo 根據指令模擬車輛前進、轉彎或停止。

### 讀取車輛位置

1. Gazebo 模擬車輛的運動狀態。
2. ROS 2 Bridge 將 Gazebo 的 Odometry 訊息轉換為 ROS 2 訊息。
3. `read_odom.py` 訂閱 `/model/vehicle_blue/odometry`。
4. 程式持續輸出車輛的 X、Y 座標與前進速度。

