cmake_minimum_required(VERSION 3.8)
project(ur5e_gripper_demo)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch urdf srdf
  DESTINATION share/${PROJECT_NAME}
)
install(FILES pick_place_world.sdf
  DESTINATION share/${PROJECT_NAME}/worlds
)

install(PROGRAMS scripts/pick_place_demo.py
  DESTINATION lib/${PROJECT_NAME}
)
ament_package()
