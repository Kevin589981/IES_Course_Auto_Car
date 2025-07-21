import RPi.GPIO as GPIO
import time
import threading
import cv2

# 导入新的电机控制模块
from motor_controller import init_gpio as init_gpio_motor
from motor_controller import PID, start_speed_monitor,\
    set_motor_speed, rotate_in_place, drive_straight, drive_with_color, \
    stop_motor, cleanup as cleanup_motor

# 导入颜色检测模块
from detect_color import init_camera, start_color_detection, \
    get_latest_color_data, cleanup as cleanup_camera

# 导入超声波模块
from detect_distance import init_i2c, measure_distance, \
    start_distance_measurement, get_latest_distance, \
    cleanup as cleanup_distance

import function

class StateManager:
    def __init__(self):
        self.current_state = 1  # 当前状态
        self.colors = {}        # 存储识别到的魔方颜色
        self.state_1_done = False  # 状态1是否完成
        self.state_2_done = False  # 状态2是否完成
        self.lost_target_time = None  # 丢失目标的时间
        self.on_target_1_time = None  # 接近目标的时间
        self.on_target_2_time = None  # 状态2接近目标的时间

    def set_state(self, new_state):
        """设置当前状态"""
        self.current_state = new_state
        print(f"状态已更改为: {new_state}")

    def reset_timers(self):
        """重置所有计时器"""
        self.lost_target_time = None
        self.on_target_1_time = None
        self.on_target_2_time = None


# 全局变量
running = True
state_manager = StateManager()  # 创建状态管理器实例
display_camera = True  # 是否显示摄像头画面
last_seen_time = None  # 上次看到魔方的时间

# 颜色识别相关参数
COLOR_CONFIRM_COUNT = 3  # 需要连续识别相同颜色的次数
color_confirm_counter = {}  # 颜色确认计数器
confirmed_color = None  # 已确认的颜色

# 避障和导航参数
MIN_DISTANCE = 20  # 最小安全距离(cm)
BEGIN_DISTANCE = 30  # 开始避障距离(cm)
ON_TAGERT_TIME = 2  # 靠近目标后的绕目标旋转时间(秒)
SIDE_OFFSET = 50   # 侧向偏移像素值(用于绕过魔方)
STRAIGHT_TIME = 2  # 通过魔方后直行的时间(秒)

# 左转和右转的颜色分类
LEFT_COLORS = ["red", "yellow"]
RIGHT_COLORS = ["blue", "green"]
# 启动显示摄像头画面的线程
# def start_display_camera():
#     """启动显示摄像头画面的线程"""
#     global display_thread
    
#     display_thread = threading.Thread(target=display_camera_thread)
#     display_thread.daemon = True  # 设为守护线程，主程序结束时自动结束
#     display_thread.start()
    
#     return display_thread

# 基于颜色检测的直线行驶函数（适配新的电机控制模块）
def drive_straight_with_color(color_offset, speed=1.5, offset_factor=0.2):
    """
    根据颜色检测的偏移量控制小车行驶
    
    Args:
        color_offset: 颜色中心相对于画面中心的偏移量
        speed: 基础速度（转/秒）
        offset_factor: 偏移影响因子，范围0到1
    """
    # 使用新模块的drive_with_color函数
    drive_with_color(color_offset, speed, offset_factor)

# 使用PID控制的原地转向函数（适配新的电机控制模块）
def rotate_in_place_with_pid(direction, target_speed=1.0):
    """
    控制小车原地转向
    
    Args:
        direction: 转向方向，'clockwise'顺时针，'counterclockwise'逆时针
        target_speed: 转向速度（转/秒）
    """
    # 使用新模块的rotate_in_place函数
    rotate_in_place(direction, target_speed)

# 使用PID控制的直线行驶函数（适配新的电机控制模块）
def drive_straight_with_pid(target_speed=1.5):
    """
    控制小车直线行驶
    
    Args:
        target_speed: 目标速度，正值表示前进，负值表示后退
    """
    # 使用新模块的drive_straight函数
    drive_straight(target_speed)


try:
    # 初始化电机
    pwma, pwmb = init_gpio_motor()
    print("电机已初始化")
    
    # 启动电机速度监测
    start_speed_monitor()
    print("电机速度监测已启动")

    init_i2c()
    start_distance_measurement()  # 启动超声波模块
    print("超声波模块已启动")
    
    # 初始化摄像头
    camera = init_camera() # 摄像头ID默认为0，可选输入摄像头ID
    if camera is None:
        print("摄像头初始化失败，程序退出")
        exit(1)
    
    # 启动颜色检测线程
    start_color_detection(interval=0.1)  # 每0.1秒检测一次
    print("颜色检测线程已启动")

    # 等待系统稳定
    print("系统初始化中，请稍候...")
    time.sleep(2)

    while 1:
        # 获取最新的颜色检测结果
        color_data = get_latest_color_data()

        # 获取超声波距离
        distance = get_latest_distance()
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
            if widest_color not in color_confirm_counter:
                color_confirm_counter[widest_color] = 1
            else:
                color_confirm_counter[widest_color] += 1
            
            # 重置其他颜色的计数
            for color in color_confirm_counter:
                if color != widest_color:
                    color_confirm_counter[color] = 0
            
            # 检查是否达到确认阈值
            if color_confirm_counter.get(widest_color, 0) >= COLOR_CONFIRM_COUNT:
                confirmed_color = widest_color
                state_manager.colors[1] = confirmed_color  # 记录状态1的颜色
                print(f"已确认魔方颜色: {confirmed_color}")
                break
            else:
                print(f"正在确认颜色: {widest_color} ({color_confirm_counter.get(widest_color, 0)}/{COLOR_CONFIRM_COUNT})")
                # 在确认过程中，慢速直行
                drive_straight(target_speed=1.5)
        else:
            # 没有检测到任何颜色，直行寻找
            print("未检测到任何颜色，直行寻找...")
            drive_straight(target_speed=1.5)

    # find_first()需要实现找到第一个方块的函数
    # left_or_right = find_first_color_and_change_to_left_or_right()

    left_or_right_color = state_manager.colors[1]
    if left_or_right_color in LEFT_COLORS:
        left_or_right = 0 
    elif left_or_right_color in RIGHT_COLORS:
        left_or_right = 1
    else:
        print("第一颜色识别错误")
    # left_or_right从前面得出

    function.straight_to_center_until()# 是否需要有一个额外线程提供给这个函数方向目标防止跑偏？
    
    function.static_turn(left_or_right)

    #begin_find_second()
    #开始找第二个魔方 可以旋转？直到视野出现第一帧可以结束  
    #是否可以在static_turn进行到一半的时候也就是第一次转弯到45度时候就开始探测？使用half_static_turn？

    #big_is_left_or_right = big_is_left_or_right()
    first_find_second_is_left_or_right = left_or_right
    #straight_to_big_center_until()

    function.static_turn(~first_find_second_is_left_or_right)

    #begin_find_thrid()
    #是否可以在static_turn进行到一半的时候就开始探测

    function.straight_to_center_until()

    #left_or_right_3 = find_third_color()

    left_or_right_3 = 0

    function.static_turn(left_or_right)
    #结束
except KeyboardInterrupt:
    print("\n程序被用户中断")
finally:
    # 停止电机
    stop_motor()
    
    # 清理资源
    cleanup_motor()
    cleanup_camera()
    cleanup_distance()
    
    print("程序已退出，资源已清理")