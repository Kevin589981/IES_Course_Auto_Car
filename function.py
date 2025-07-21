import time
def get_latest_distance():
    global distance
    return distance

def set_motor_speed( left = 0.5, right =0.5 ):
    pass

def straight_to_center_until():
    # 直行模块，直行至25cm远处执行
    order_distance = 25
    while 1:
        time.sleep(0.1)
        distance = get_latest_distance()
        if distance < order_distance:
            return
left_or_right = 0

def static_turn(left_or_right):
    # 静态拐弯，传入left_or_right 为0或1 0=左绕行 1=右绕行
    speed = 1
    double_speed = 2 * speed
    if left_or_right == 0:# 左绕行
        print("开始左绕行")
        set_motor_speed(speed,double_speed)
        time.sleep(0.5)
        set_motor_speed(double_speed,speed)
        time.sleep(1)
        set_motor_speed(speed,double_speed)
        time.sleep(0.5)
        return
    elif left_or_right == 1:
        print("开始左绕行")
        set_motor_speed(double_speed,speed)
        time.sleep(0.5)
        set_motor_speed(speed,double_speed)
        time.sleep(1)
        set_motor_speed(double_speed,speed)
        time.sleep(0.5)
        return
    else:
        print("static_turn接受参数不合理")

def half_static_turn(left_or_right):
    speed = 1
    double_speed = 2 * speed
    if left_or_right == 0:# 左绕行
        print("开始左绕行")
        set_motor_speed(speed,double_speed)
        time.sleep(0.5)
        set_motor_speed(double_speed,speed)
        return
    elif left_or_right == 1:
        print("开始左绕行")
        set_motor_speed(double_speed,speed)
        time.sleep(0.5)
        set_motor_speed(speed,double_speed)
        return
    else:
        print("half_static_turn接受参数不合理")