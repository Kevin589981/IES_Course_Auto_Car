#! /usr/bin/env python3
# main_controller6.py
# 顺序执行版本的控制器 - 使用矩形路径绕行

import RPi.GPIO as GPIO
import time
import threading
import cv2

# 导入电机控制模块
from motor_controller import init_gpio, start_speed_monitor, start_pwm_update_daemon, \
    set_motor_speed, rotate_in_place, drive_straight, drive_with_color, \
    stop_motor, cleanup as cleanup_motor

# 导入颜色检测模块
from detect_color import init_camera, start_color_detection, \
    get_latest_color_data, cleanup as cleanup_camera

# 导入超声波模块
from detect_distance import init_i2c, measure_distance, \
    start_distance_measurement, get_latest_distance, \
    cleanup as cleanup_distance

# ===== 可配置参数（修改此处无需改动函数） =====
# 1. 状态控制参数
COLOR_CONFIRM_COUNT = 3  # 需要连续识别相同颜色的次数
DISTANCE_THRESHOLD = 55.0  # 接近魔方的距离阈值(cm)
SEARCH_SPEED = 0.4  # 搜索魔方时的旋转速度
FORWARD_SPEED = 1.0  # 直行速度
TURN_SPEED = 0.8  # 转弯速度
turn_time = 1.2

# 2. 绕行参数
# TURN_LEFT_TIME = 0.3  # 原地转弯时间(秒)，大约90度
# TURN_RIGHT_TIME = 0.4
# left参数
LEFT_TIME_1 = 0.45
LEFT_TIME_2 = 0.35
LEFT_TIME_3 = 0#0.3
LEFT_TIME_4 = 0#0.4

# right参数
RIGHT_TIME_1 = 0.25 
RIGHT_TIME_2 = 0.35
RIGHT_TIME_3 = 0#0.4
RIGHT_TIME_4 = 0#0.4

SIDE_A_TIME = 0.85  # 矩形短边行驶时间(秒)
SIDE_B_TIME = 3  # 矩形长边行驶时间(秒)
FINAL_SPRINT_SPEED = 0.5  # 最终冲刺速度

# 3. 颜色分类
LEFT_TURN_COLORS = ["red", "yellow"]  # 左转颜色
RIGHT_TURN_COLORS = ["blue", "green"]  # 右转颜色

global dismiss_end

# 4. 显示参数
DISPLAY_CAMERA = False # 是否显示摄像头画面

# 状态管理类
class StateManager:
    def __init__(self):
        # 基本状态
        self.current_state = 1  # 当前状态(1,2,3)
        self.detected_color = None  # 当前检测到的颜色
        self.color_confirm_counter = {}  # 颜色确认计数器
        self.last_bypass_direction = None  # 上一次绕行方向('left'或'right')
        
        # 阶段完成标志
        self.state1_done = False
        self.state2_done = False
        self.state3_done = False

    def determine_bypass_direction(self):
        """确定绕行方向"""
        if self.current_state == 1:
            # 状态1: 根据颜色决定
            if self.detected_color in LEFT_TURN_COLORS:
                direction = 'left'
            else:
                direction = 'right'
        elif self.current_state == 2:
            # 状态2: 与上一次相反
            if self.last_bypass_direction == 'left':
                direction = 'right'
            else:
                direction = 'left'
        else:  # 状态3
            # 状态3: 根据颜色决定
            if self.detected_color in LEFT_TURN_COLORS:
                direction = 'left'
            else:
                direction = 'right'
                
        self.last_bypass_direction = direction
        return direction

# 全局变量
running = True
state_manager = StateManager()
display_thread = None
global camera
# 显示摄像头画面的线程函数
def display_camera_thread():
    """显示摄像头实时画面的线程函数"""
    global running
    
    if not 'camera' in globals() or camera is None:
        print("错误: 摄像头未初始化，无法显示画面")
        return
    
    print("摄像头显示线程已启动")
    
    # 创建窗口
    cv2.namedWindow("摄像头画面", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("摄像头画面", 640, 480)
    
    while running and DISPLAY_CAMERA:
        # 读取一帧图像
        ret, frame = camera.read()
        if not ret:
            print("警告: 无法从摄像头读取图像")
            time.sleep(0.1)
            continue
        
        # 获取最新的颜色检测结果，在画面上标记出来
        color_data = get_latest_color_data()
        
        # 在画面上标记检测到的颜色区域
        for color, segments in color_data.items():
            for segment in segments:
                x_start, x_end, x_center = segment
                # 计算y坐标（根据detect_color.py中的DEFAULT_ROW_PERCENT和DEFAULT_ROW_HEIGHT）
                height = frame.shape[0]
                row_percent = 0.5  # 默认值，与detect_color.py中保持一致
                row_height = 10    # 默认值，与detect_color.py中保持一致
                y_center = int(height * row_percent)
                
                # 在图像上绘制矩形标记颜色区域
                color_rgb = (0, 0, 255)  # 默认红色
                if color == "red":
                    color_rgb = (0, 0, 255)
                elif color == "green":
                    color_rgb = (0, 255, 0)
                elif color == "blue":
                    color_rgb = (255, 0, 0)
                elif color == "yellow":
                    color_rgb = (0, 255, 255)
            
                cv2.rectangle(frame, (x_start + frame.shape[1]//2, y_center-row_height//2), 
                             (x_end + frame.shape[1]//2, y_center+row_height//2), color_rgb, 2)
                cv2.putText(frame, color, (x_start + frame.shape[1]//2, y_center-15), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_rgb, 2)
        
        # 显示距离信息
        distance = get_latest_distance()
        cv2.putText(frame, f"距离: {distance:.1f} cm", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 显示当前状态
        cv2.putText(frame, f"状态: {state_manager.current_state}", (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 显示检测到的颜色
        if state_manager.detected_color:
            cv2.putText(frame, f"颜色: {state_manager.detected_color}", (10, 90), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 显示绕行方向
        if state_manager.last_bypass_direction:
            cv2.putText(frame, f"绕行: {state_manager.last_bypass_direction}", (10, 120), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 显示图像
        cv2.imshow("摄像头画面", frame)
        
        # 按下q键退出
        if cv2.waitKey(1) & 0xFF == ord('q'):
            running = False
            break
        
        # 控制帧率
        time.sleep(0.03)  # 约30fps
    
    # 关闭窗口
    cv2.destroyAllWindows()
    print("摄像头显示线程已停止")

# 启动显示摄像头画面的线程
def start_display_camera():
    """启动显示摄像头画面的线程"""
    global display_thread
    
    if DISPLAY_CAMERA:
        display_thread = threading.Thread(target=display_camera_thread)
        display_thread.daemon = True  # 设为守护线程，主程序结束时自动结束
        display_thread.start()
        return display_thread
    return None

# # 顺序执行的矩形路径绕行函数
# def execute_bypass_rectangular_old(direction):
#     """
#     使用矩形路径顺序执行绕行动作，不使用循环
    
#     Args:
#         direction: 绕行方向，'left'或'right'
#     """
#     print(f"开始{direction}侧矩形路径绕行")
    
#     # 第1步：原地转向90度
#     print("执行第1步：原地转向90度")
#     if direction == 'left':
#         # 左转90度
#         rotate_in_place('counterclockwise', TURN_SPEED)
#         time.sleep(TURN_LEFT_TIME)
#     else:
#         # 右转90度
#         rotate_in_place('clockwise', TURN_SPEED)
#         time.sleep(TURN_RIGHT_TIME)
    
#     # 第2步：直行短边A
#     print("执行第2步：直行短边A")
#     drive_straight(FORWARD_SPEED)
#     time.sleep(SIDE_A_TIME)
    
#     # 第3步：原地转向90度（转回朝向与魔方平行的方向）
#     print("执行第3步：原地转向90度")
#     if direction == 'left':
#         # 右转90度
#         rotate_in_place('clockwise', TURN_SPEED)
#         time.sleep(TURN_RIGHT_TIME)
#     else:
#         # 左转90度
#         rotate_in_place('counterclockwise', TURN_SPEED)
#         time.sleep(TURN_LEFT_TIME)
    
#     # 第4步：直行长边B
#     print("执行第4步：直行长边B")
#     drive_straight(FORWARD_SPEED)
#     time.sleep(SIDE_B_TIME)
    
#     # 第5步：原地转向90度（准备回到原来的路线）
#     print("执行第5步：原地转向90度")
#     if direction == 'left':
#         # 右转90度
#         rotate_in_place('clockwise', TURN_SPEED)
#         time.sleep(TURN_RIGHT_TIME)
#     else:
#         # 左转90度
#         rotate_in_place('counterclockwise', TURN_SPEED)
#         time.sleep(TURN_LEFT_TIME)
    
#     # 第6步：直行短边A
#     print("执行第6步：直行短边A")
#     drive_straight(FORWARD_SPEED)
#     time.sleep(SIDE_A_TIME)
    
#     # 第7步：原地转向90度（回到原来的前进方向）
#     print("执行第7步：原地转向90度")
#     if direction == 'left':
#         # 左转90度
#         rotate_in_place('counterclockwise', TURN_SPEED+0.2)
#         time.sleep(TURN_LEFT_TIME)
#     else:
#         # 右转90度
#         rotate_in_place('clockwise', TURN_SPEED)
#         time.sleep(TURN_RIGHT_TIME)
    
#     set_motor_speed(0.5,0.5)
#     time.sleep(1)

#     # 绕行完成，停车
#     #set_motor_speed(0, 0)
#     print("矩形路径绕行完成")

# 顺序执行的矩形路径绕行函数（改进版，每个转弯时间独立可调）
def execute_bypass_rectangular(direction):
    """
    使用矩形路径顺序执行绕行动作，每个转弯时间独立可调
    
    Args:
        direction: 绕行方向，'left'或'right'
    """
    print(f"开始{direction}侧矩形路径绕行")
    
    if direction == 'left':
        # 左侧绕行路径
        
        # 第1步：原地左转90度
        print("执行第1步：原地左转90度")
        rotate_in_place('counterclockwise', TURN_SPEED)
        time.sleep(LEFT_TIME_1)  # 左转第1次时间
        
        # 第2步：直行短边A
        print("执行第2步：直行短边A")
        drive_straight(FORWARD_SPEED)
        time.sleep(SIDE_A_TIME)
        
        # 第3步：原地右转90度（转回朝向与魔方平行的方向）
        print("执行第3步：原地右转90度")
        rotate_in_place('clockwise', TURN_SPEED)
        time.sleep(LEFT_TIME_2)  # 右转第1次时间
        
        # 第4步：直行长边B
        print("执行第4步：直行长边B")
        drive_straight(FORWARD_SPEED)
        time.sleep(SIDE_B_TIME)
        
        # # 第5步：原地右转90度（准备回到原来的路线）
        # print("执行第5步：原地右转90度")
        # rotate_in_place('clockwise', TURN_SPEED)
        # time.sleep(LEFT_TIME_3)  # 右转第2次时间
        
        # # 第6步：直行短边A
        # print("执行第6步：直行短边A")
        # drive_straight(FORWARD_SPEED)
        # time.sleep(SIDE_A_TIME)
        
        # # 第7步：原地左转90度（回到原来的前进方向）
        # print("执行第7步：原地左转90度")
        # rotate_in_place('counterclockwise', TURN_SPEED)
        # time.sleep(LEFT_TIME_4)  # 左转第2次时间
        
    elif direction == 'right':
        # 右侧绕行路径
        
        # 第1步：原地右转90度
        print("执行第1步：原地右转90度")
        rotate_in_place('clockwise', TURN_SPEED)
        time.sleep(RIGHT_TIME_1)  # 右转第1次时间
        
        # 第2步：直行短边A
        print("执行第2步：直行短边A")
        drive_straight(FORWARD_SPEED)
        time.sleep(SIDE_A_TIME)
        
        # 第3步：原地左转90度（转回朝向与魔方平行的方向）
        print("执行第3步：原地左转90度")
        rotate_in_place('counterclockwise', TURN_SPEED)
        time.sleep(RIGHT_TIME_2)  # 左转第1次时间
        
        # 第4步：直行长边B
        print("执行第4步：直行长边B")
        drive_straight(FORWARD_SPEED)
        time.sleep(SIDE_B_TIME)
        
        # # 第5步：原地左转90度（准备回到原来的路线）
        # print("执行第5步：原地左转90度")
        # rotate_in_place('counterclockwise', TURN_SPEED)
        # time.sleep(RIGHT_TIME_3)  # 左转第2次时间
        
        # # 第6步：直行短边A
        # print("执行第6步：直行短边A")
        # drive_straight(FORWARD_SPEED)
        # time.sleep(SIDE_A_TIME)
        
        # # 第7步：原地右转90度（回到原来的前进方向）
        # print("执行第7步：原地右转90度")
        # rotate_in_place('clockwise', TURN_SPEED)
        # time.sleep(RIGHT_TIME_4)  # 右转第2次时间
    
    # 最后稳定一下
    set_motor_speed(0.5, 0.5)
    time.sleep(1)

    # 绕行完成，停车
    # #set_motor_speed(0, 0)
    print("矩形路径绕行完成")

# 颜色检测函数
def detect_and_confirm_color():
    """
    检测并确认颜色
    
    Returns:
        str: 确认的颜色，如果未确认则返回None
    """
    # 获取最新的颜色检测结果
    color_data = get_latest_color_data()
    
    if not color_data:
        # 重置颜色计数器
        state_manager.color_confirm_counter = {}
        return None
    
    # 找到最宽的颜色块作为目标魔方
    widest_color = None
    max_width = 0
    
    for color, segments in color_data.items():
        if segments:  # 确保有检测到该颜色
            for segment in segments:  
                width = abs(segment[1] - segment[0])  # 计算宽度
                if width > max_width:
                    max_width = width
                    widest_color = color
    
    if widest_color:
        # 颜色确认逻辑
        if widest_color not in state_manager.color_confirm_counter:
            state_manager.color_confirm_counter[widest_color] = 1
        else:
            state_manager.color_confirm_counter[widest_color] += 1
        
        # 重置其他颜色的计数
        for color in list(state_manager.color_confirm_counter.keys()):
            if color != widest_color:
                state_manager.color_confirm_counter[color] = 0
        
        # 检查是否达到确认阈值
        if state_manager.color_confirm_counter.get(widest_color, 0) >= COLOR_CONFIRM_COUNT:
            return widest_color
    
    return None

# 顺序执行的搜索魔方函数
def search_for_cube_sequential():
    """
    顺序执行搜索魔方，先左转一段时间，再右转一段时间
    """
    print("开始搜索魔方，第1阶段：左转")
    
    # 第1阶段：左转
    rotate_in_place('counterclockwise', SEARCH_SPEED)
    search_start_time = time.time()
    turn_back_time = 0
    
    # 在左转过程中检测颜色
    while time.time() - search_start_time < turn_time:  # 最多左转3秒
        confirmed_color = detect_and_confirm_color()
        if confirmed_color:
            # set_motor_speed(0, 0)
            print(f"在左转过程中找到魔方颜色: {confirmed_color}")
            turn_back_time = time.time() - search_start_time
            # return confirmed_color
            break
        time.sleep(0.1)
    
    # 回正
    if confirmed_color and turn_back_time > 0:
        print("开始回正")
        rotate_in_place('clockwise', SEARCH_SPEED)
        time.sleep(turn_back_time)
        # set_motor_speed(0, 0)
        return confirmed_color
    
    # 如果左转没找到，切换到右转
    print("切换到第2阶段：右转")
    rotate_in_place('clockwise', SEARCH_SPEED)
    search_start_time = time.time()
    
    # 在右转过程中检测颜色
    while time.time() - search_start_time < 2*turn_time:  # 最多右转6秒(覆盖整个360度)
        confirmed_color = detect_and_confirm_color()
        if confirmed_color:
            # set_motor_speed(0, 0)
            print(f"在右转过程中找到魔方颜色: {confirmed_color}")
            turn_back_time = 2 * turn_time + search_start_time - time.time()
            # return confirmed_color
            break
        time.sleep(0.1)

    # 回正
    if confirmed_color and turn_back_time != 0:
        print("开始回正")
        if turn_back_time > 0:
            rotate_in_place('clockwise', SEARCH_SPEED)
            time.sleep(turn_back_time)
        else:
            rotate_in_place('counterclockwise', SEARCH_SPEED)
            time.sleep(-turn_back_time)
        # set_motor_speed(0, 0)
        return confirmed_color
    
    # 如果还是没找到，停止搜索
    # set_motor_speed(0, 0)
    print("搜索结束，未找到魔方")
    return None

# 顺序执行的接近魔方函数
def approach_cube_sequential(color):
    """
    顺序执行接近魔方，直到达到指定距离
    
    Args:
        color: 目标魔方颜色
    
    Returns:
        bool: 是否成功接近魔方
    """
    print(f"开始接近{color}魔方")
    
    # 设置超时时间，防止无限循环
    approach_start_time = time.time()
    max_approach_time = 30.0  # 最多接近30秒
    
    while time.time() - approach_start_time < max_approach_time:
        # 获取最新的颜色检测结果
        color_data = get_latest_color_data()
        
        # 获取超声波距离
        distance = get_latest_distance()
        
        # 检查是否已经接近魔方
        if distance <= DISTANCE_THRESHOLD and distance > 0:
            #set_motor_speed(0, 0)
            print(f"已接近魔方，距离: {distance}cm")
            return True
        
        # 使用颜色偏移量控制小车行驶
        color_segments = color_data.get(color, [])
        if color_segments:
            # 使用最宽的颜色段的中心点作为导航目标
            widest_segment = max(color_segments, key=lambda s: abs(s[1] - s[0]))
            x_center = widest_segment[2]  # 获取中心点偏移量
            drive_with_color(x_center, FORWARD_SPEED)
        else:
            # 如果看不到目标颜色，直行
            drive_straight(FORWARD_SPEED)
        
        # 短暂暂停，避免CPU占用过高
        time.sleep(0.1)
    
    # 如果超时，停车
    #set_motor_speed(0, 0)
    print("接近魔方超时")
    return False

# 顺序执行的状态1处理函数
def handle_state1_sequential():
    """
    顺序执行状态1：识别并通过第一个魔方
    """
    print("开始执行状态1: 识别并通过第一个魔方")
    set_motor_speed(1, 1)
    time.sleep(0.5)
    print("启动")
    set_motor_speed(0.3,0.3)

    # 步骤1: 检测并确认颜色
    while True:
        confirmed_color = detect_and_confirm_color()
        if confirmed_color:
            state_manager.detected_color = confirmed_color
            print(f"确认魔方颜色: {confirmed_color}")
            break
        time.sleep(0.1)
    #set_motor_speed(0,0)

    # 步骤2: 接近魔方
    approach_success = approach_cube_sequential(state_manager.detected_color)
    if not approach_success:
        print("接近魔方失败，状态1未完成")
        return False
    
    # 步骤3: 确定绕行方向
    bypass_direction = state_manager.determine_bypass_direction()
    print(f"决定{bypass_direction}侧绕行")
    
    # 步骤4: 执行矩形路径绕行
    execute_bypass_rectangular(bypass_direction)
    
    # 状态1完成
    state_manager.state1_done = True
    print("状态1完成")
    return True

# 顺序执行的状态2处理函数
def handle_state2_sequential():
    """
    顺序执行状态2：识别并通过第二个魔方
    """
    print("开始执行状态2: 识别并通过第二个魔方")

    dismiss_end = True
    
    # 步骤1: 搜索并确认颜色
    set_motor_speed(0.3,0.3)

    confirmed_color = search_for_cube_sequential()
    if not confirmed_color:
        print("搜索魔方失败，状态2未完成，保持直行")
        set_motor_speed(1.0, 1.0)
        time.sleep(2)
        print("阶段2直行完成")
        state_manager.state2_done = True
        # return False
        return True
    
    state_manager.detected_color = confirmed_color
    
    # 步骤2: 接近魔方
    approach_success = approach_cube_sequential(state_manager.detected_color)
    if not approach_success:
        print("接近魔方失败，状态2未完成")
        return False
    
    # 步骤3: 确定绕行方向（与状态1相反）
    bypass_direction = state_manager.determine_bypass_direction()
    print(f"决定{bypass_direction}侧绕行")
    
    # 步骤4: 执行矩形路径绕行
    execute_bypass_rectangular(bypass_direction)
    
    # 状态2完成
    state_manager.state2_done = True
    print("状态2完成")
    return True

# 顺序执行的状态3处理函数
def handle_state3_sequential():
    """
    顺序执行状态3：识别并通过第三个魔方
    """
    print("开始执行状态3: 识别并通过第三个魔方")

    dismiss_end = False

    set_motor_speed(0.3,0.3)
    time.sleep(0.5)
    # 步骤1: 搜索并确认颜色
    confirmed_color = search_for_cube_sequential()
    if not confirmed_color:
        print("搜索魔方失败，状态3未完成，保持直行")
        set_motor_speed(1.0, 1.0)
        time.sleep(2)
        state_manager.state3_done = True
        # return False
        return True
    
    state_manager.detected_color = confirmed_color
    
    # 步骤2: 接近魔方
    approach_success = approach_cube_sequential(state_manager.detected_color)
    if not approach_success:
        print("接近魔方失败，状态3未完成")
        return False
    
    # 步骤3: 确定绕行方向
    bypass_direction = state_manager.determine_bypass_direction()
    print(f"决定{bypass_direction}侧绕行")
    
    # 步骤4: 执行矩形路径绕行
    execute_bypass_rectangular(bypass_direction)
    
    # 状态3完成
    state_manager.state3_done = True
    print("状态3完成")
    return True

# 顺序执行的最终冲刺函数
def final_sprint_sequential():
    """
    顺序执行最终冲刺
    """
    print("开始最终冲刺")
    
    # 直行一段时间
    drive_straight(FINAL_SPRINT_SPEED)
    time.sleep(3.0)  # 冲刺3秒
    
    # 停车
    #set_motor_speed(0, 0)
    print("最终冲刺完成")

# 主控制函数（顺序执行版本）
def main_control_sequential():
    """顺序执行的主控制函数"""
    global running, camera
    
    try:
        # 初始化电机
        init_gpio()
        print("电机已初始化")
        
        # 启动电机速度监测和PWM更新
        start_speed_monitor()
        start_pwm_update_daemon()
        print("电机速度监测和PWM更新已启动")
        
        # 初始化I2C设备（超声波）
        init_i2c()
        print("I2C设备已初始化")
        
        # 启动距离测量线程
        start_distance_measurement()
        print("距离测量线程已启动")
        
        # 初始化摄像头
        camera = init_camera()
        if camera is None:
            print("摄像头初始化失败，程序退出")
            return
        print("摄像头已初始化")
        
        # 启动颜色检测线程
        start_color_detection()
        print("颜色检测线程已启动")
        
        # 启动显示摄像头画面的线程
        if DISPLAY_CAMERA:
            start_display_camera()
            print("摄像头画面显示已启动")
        
        # 等待系统稳定
        print("系统初始化中，请稍候...")
        time.sleep(2)
        
        # 顺序执行各个状态
        
        # 状态1: 识别并通过第一个魔方
        state_manager.current_state = 1
        if not handle_state1_sequential():
            print("状态1执行失败，程序退出")
            return
        
        # 状态2: 识别并通过第二个魔方
        state_manager.current_state = 2
        if not handle_state2_sequential():
            print("状态2执行失败，程序退出")
            return
        
        # 状态3: 识别并通过第三个魔方
        state_manager.current_state = 3
        if not handle_state3_sequential():
            print("状态3执行失败，程序退出")
            return
        
        # 最终冲刺
        final_sprint_sequential()
        
        print("任务完成！")
    
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序出错: {e}")
    finally:
        # 停止电机
        #set_motor_speed(0, 0)
        
        # 清理资源
        cleanup_motor()
        cleanup_camera()
        cleanup_distance()
        
        print("程序结束，资源已清理")

# 程序入口
if __name__ == "__main__":
    main_control_sequential()