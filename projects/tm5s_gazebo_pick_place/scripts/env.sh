# Source ROS 2 Jazzy, the Techman packages (tm_ws) and this project's workspace.
source /opt/ros/jazzy/setup.bash
source "${TM_WS:-$HOME/tm_ws}/install/setup.bash"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ros2_ws/install/setup.bash"
