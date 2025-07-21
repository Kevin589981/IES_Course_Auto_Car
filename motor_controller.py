# motor_controller.py
from sys import set_asyncgen_hooks
import RPi.GPIO as GPIO
import time
import threading
import numpy as np
import matplotlib.pyplot as plt

# 引脚定义
EA, I2, I1, EB, I3, I4, LS, RS = (13, 19, 26, 16, 20, 21, 6, 12)
#EA, I4, I3, EB, I1, I2, LS, RS = (13, 19, 26, 16, 20, 21, 6, 12)
FREQUENCY = 100  # PWM频率100Hz，使电机转动更平滑

# 速度计数器变量
lspeed = 0  # 左轮实际速度
rspeed = 0  # 右轮实际速度
lcounter = 0
rcounter = 0

# 全局PWM对象
pwma_global = None
pwmb_global = None

# 全局PID控制器
left_pid_global = None
right_pid_global = None

# 运行标志
running = True

# 目标速度变量
left_target_speed = 0
right_target_speed = 0

# 初始化GPIO
def init_gpio()-> tuple:
    global pwma_global, pwmb_global
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setup([EA, I2, I1, EB, I4, I3], GPIO.OUT)
    GPIO.setup([LS, RS], GPIO.IN)
    
    # 初始化PWM
    pwma = GPIO.PWM(EA, FREQUENCY)
    pwmb = GPIO.PWM(EB, FREQUENCY)
    pwma.start(0)
    pwmb.start(0)
    
    # 保存全局引用
    pwma_global = pwma
    pwmb_global = pwmb
    
    return pwma, pwmb

# 编码器回调函数
def encoder_callback(channel)-> None:
    global lcounter, rcounter
    if channel == LS:
        lcounter += 1
    elif channel == RS:
        rcounter += 1

# 速度监测线程函数
def speed_monitor(interval=0.1):
    global rspeed, lspeed, lcounter, rcounter
    GPIO.add_event_detect(LS, GPIO.RISING, callback=encoder_callback)
    GPIO.add_event_detect(RS, GPIO.RISING, callback=encoder_callback)
    
    while running:
        # 计算每秒转速
        rspeed = (rcounter / 585.0)  # 585脉冲/圈
        lspeed = (lcounter / 585.0)
        rcounter = 0
        lcounter = 0
        # print(rspeed, " ",lspeed)
        # print(left_target_speed," ",right_target_speed)
        time.sleep(interval)

# 启动速度监测
def start_speed_monitor():
    thread = threading.Thread(target=speed_monitor)
    thread.daemon = True  # 设为守护线程，主程序结束时自动结束
    thread.start()
    return thread

# 新增：PWM更新守护进程
def pwm_update_daemon(interval=0.1):
    """
    PWM更新守护进程，每隔interval秒更新一次电机PWM值
    
    Args:
        interval: 更新间隔时间（秒）
    """
    global left_pid_global, right_pid_global, lspeed, rspeed, left_target_speed, right_target_speed
    
    while running:
        # 如果PID控制器已初始化且有目标速度
        if left_pid_global is not None and right_pid_global is not None:
            # 计算PWM值
            left_pwm = left_pid_global.update(lspeed)
            right_pwm = right_pid_global.update(rspeed)
            
            # 根据目标速度的正负设置方向
            if left_target_speed < 0:
                left_pwm = -left_pwm
            if right_target_speed < 0:
                right_pwm = -right_pwm
            
            # 设置电机PWM
            _set_motor_pwm(left_pwm, right_pwm)
            
        # 等待指定的间隔时间
        time.sleep(interval)

# 启动PWM更新守护进程
def start_pwm_update_daemon():
    """启动PWM更新守护进程"""
    thread = threading.Thread(target=pwm_update_daemon)
    thread.daemon = True  # 设为守护线程，主程序结束时自动结束
    thread.start()
    return thread

class PID:
    """PID控制器"""

    def __init__(self, P=38.57, I=0.1, D=70, speed=0.5):
        self.Kp = P
        self.Ki = I
        self.Kd = D
        self.err_pre = 0
        self.err_last = 0
        self.u = 0
        self.integral = 0
        self.ideal_speed = speed
    
    def update(self, feedback_value):
        self.err_pre = self.ideal_speed - feedback_value
        self.integral += self.err_pre
        self.u = self.Kp*self.err_pre + self.Ki*self.integral + self.Kd*(self.err_pre-self.err_last)
        self.err_last = self.err_pre
        
        if self.u > 100:
            self.u = 100
        elif self.u < 0:
            self.u = 0
        return self.u

    def setKp(self, proportional_gain):
        """设置比例增益"""
        self.Kp = proportional_gain

    def setKi(self, integral_gain):
        """设置积分增益"""
        self.Ki = integral_gain

    def setKd(self, derivative_gain):
        """设置微分增益"""
        self.Kd = derivative_gain
        
    def reset(self):
        """重置PID控制器状态"""
        self.err_pre = 0
        self.err_last = 0
        self.integral = 0
        self.u = 0
        
    def set_target_speed(self, speed):
        """设置目标速度"""
        self.ideal_speed = speed

# 直接设置电机PWM占空比（内部使用）
def _set_motor_pwm(left=0, right=0):
    """
    直接设置左右电机的PWM占空比
    
    Args:
        left: 左电机PWM占空比，范围-100到100，负值表示反转
        right: 右电机PWM占空比，范围-100到100，负值表示反转
    """
    global pwma_global, pwmb_global
    
    # 确保PWM对象已初始化
    if pwma_global is None or pwmb_global is None:
        print("错误: 电机PWM未初始化，请先调用init_gpio()")
        return
    
    # 控制左电机方向和速度
    if left >= 0:
        GPIO.output(I3, GPIO.HIGH)
        GPIO.output(I4, GPIO.LOW)
        pwmb_global.ChangeDutyCycle(min(abs(left), 100))
    else:
        GPIO.output(I3, GPIO.LOW)
        GPIO.output(I4, GPIO.HIGH)
        pwmb_global.ChangeDutyCycle(min(abs(left), 100))
    
    # 控制右电机方向和速度
    if right >= 0:
        GPIO.output(I1, GPIO.HIGH)
        GPIO.output(I2, GPIO.LOW)
        pwma_global.ChangeDutyCycle(min(abs(right), 100))
    else:
        GPIO.output(I1, GPIO.LOW)
        GPIO.output(I2, GPIO.HIGH)
        pwma_global.ChangeDutyCycle(min(abs(right), 100))

# 基于速度的电机控制（使用PID）
def set_motor_speed(left_target=0.5, right_target=0.5):
    """
    设置左右电机的目标速度（使用PID控制）
    
    Args:
        left_target: 左电机目标速度（转/秒），正值表示前进，负值表示后退
        right_target: 右电机目标速度（转/秒），正值表示前进，负值表示后退
    """
    global left_pid_global, right_pid_global, left_target_speed, right_target_speed
    
    # 更新全局目标速度变量
    left_target_speed = left_target
    right_target_speed = right_target
    
    # 如果PID控制器未初始化，创建新的
    if left_pid_global is None:
        left_pid_global = PID(P=45, I=0.1, D=70, speed=abs(left_target))
    else:
        left_pid_global.set_target_speed(abs(left_target))
        
    if right_pid_global is None:
        right_pid_global = PID(P=40, I=0.1, D=70, speed=abs(right_target))
    else:
        right_pid_global.set_target_speed(abs(right_target))
    
    # 注意：不再在这里直接计算PWM值和调用_set_motor_pwm
    # PWM更新由守护进程负责
    
    return abs(left_target), abs(right_target)  # 返回目标速度的绝对值

# 使用原地转向函数
def rotate_in_place(direction, speed=0.5):
    """
    控制小车原地转向
    
    Args:
        direction: 转向方向，'clockwise'顺时针，'counterclockwise'逆时针
        speed: 转向速度（转/秒）
    """
    if direction == 'clockwise':
        # 左轮正转，右轮反转
        set_motor_speed(speed, -speed)
    elif direction == 'counterclockwise':
        # 左轮反转，右轮正转
        set_motor_speed(-speed, speed)
    else:
        print("方向参数错误，应为'clockwise'或'counterclockwise'")

# 直线行驶函数
def drive_straight(speed=0.5):
    """
    控制小车直线行驶
    
    Args:
        speed: 行驶速度（转/秒），正值表示前进，负值表示后退
    """
    set_motor_speed(speed, speed)

# 基于颜色检测的直线行驶函数
def drive_with_color(color_offset, speed=0.5, offset_factor=0.2):
    """
    根据颜色检测的偏移量控制小车行驶
    
    Args:
        color_offset: 颜色中心相对于画面中心的偏移量
        speed: 基础速度（转/秒）
        offset_factor: 偏移影响因子，范围0到1
    """
    left_speed = speed
    right_speed = speed
    
    # 归一化偏移量，使其范围在0-1之间
    normalized_offset = min(1.0, abs(color_offset) / 200.0)
    
    if color_offset > 0:
        # 目标在右侧，减小右轮速度
        right_speed = speed * (1 - offset_factor * normalized_offset)
    else:
        # 目标在左侧，减小左轮速度
        left_speed = speed * (1 - offset_factor * normalized_offset)
    
    set_motor_speed(left_speed, right_speed)

# 停止电机
def stop_motor():
    """停止电机"""
    if left_pid_global is not None:
        left_pid_global.reset()
    if right_pid_global is not None:
        right_pid_global.reset()
    _set_motor_pwm(0, 0)

# 清理函数
def cleanup():
    """清理资源"""
    global running
    running = False
    time.sleep(0.2)  # 等待线程结束
    
    # 停止电机
    if pwma_global is not None and pwmb_global is not None:
        stop_motor()
        pwma_global.stop()
        pwmb_global.stop()
    
    GPIO.cleanup()

# ===== 测试代码 =====
if __name__ == "__main__":
    try:
        # 初始化GPIO和PWM
        pwma, pwmb = init_gpio()
        
        # 启动速度监测线程
        monitor_thread = start_speed_monitor()
        
        # 启动PWM更新守护进程
        pwm_update_thread = start_pwm_update_daemon()
        
        # 默认参数
        speed = 1.0  # 默认速度改为0.5转/秒
        color_offset = 0
        offset_factor = 0.2
        
        print("=== 电机控制测试程序 ===")
        print("按键说明:")
        print("w: 直线前进")
        print("s: 直线后退")
        print("a: 逆时针旋转")
        print("d: 顺时针旋转")
        print("c: 颜色跟踪模式")
        print("q: 停止电机")
        print("+-: 调整速度 (当前: {:.2f}转/秒)".format(speed))
        print("o: 设置颜色偏移量 (当前: {})".format(color_offset))
        print("f: 调整偏移因子 (当前: {:.1f})".format(offset_factor))
        print("p: 显示当前速度")
        print("x: 退出程序")
        
        # 记录数据用于绘图
        time_data = []
        left_speed_data = []
        right_speed_data = []
        left_pwm_data = []
        right_pwm_data = []
        start_time = time.time()
        record_data = False
        
        # 主循环
        while True:
            # 显示当前速度
            print("\r左轮速度: {:.2f} 右轮速度: {:.2f} 当前设置: {:.2f}转/秒 偏移: {}".format(
                lspeed, rspeed, speed, color_offset), end="")
            
            # 记录数据
            if record_data:
                current_time = time.time() - start_time
                time_data.append(current_time)
                left_speed_data.append(lspeed)
                right_speed_data.append(rspeed)
                if left_pid_global and right_pid_global:
                    left_pwm_data.append(left_pid_global.u)
                    right_pwm_data.append(right_pid_global.u)
                else:
                    left_pwm_data.append(0)
                    right_pwm_data.append(0)
            
            # 获取键盘输入
            cmd = input("\n请输入命令: ").strip().lower()
            
            if cmd == 'x':
                print("退出程序...")
                break
                
            elif cmd == 'w':
                print("直线前进")
                drive_straight(speed)
                
            elif cmd == 's':
                print("直线后退")
                drive_straight(-speed)
                
            elif cmd == 'c':
                print("颜色跟踪模式, 偏移量: {}".format(color_offset))
                drive_with_color(color_offset, speed, offset_factor)
                
            elif cmd == 'a':
                print("逆时针旋转")
                rotate_in_place('counterclockwise', speed)
                
            elif cmd == 'd':
                print("顺时针旋转")
                rotate_in_place('clockwise', speed)
                
            elif cmd == 'q':
                print("停止电机")
                stop_motor()
                
            elif cmd == '+':
                speed = min(2.0, speed + 0.1)
                print("速度增加到: {:.2f}转/秒".format(speed))
                
            elif cmd == '-':
                speed = max(0.1, speed - 0.1)
                print("速度减小到: {:.2f}转/秒".format(speed))
            elif cmd =='r':
                set_motor_speed(1,0)
           
            elif cmd == 'o':
                try:
                    new_offset = float(input("请输入新的颜色偏移量 (-200 到 200): "))
                    if -200 <= new_offset <= 200:
                        color_offset = new_offset
                        print("颜色偏移量设置为: {}".format(color_offset))
                    else:
                        print("偏移量超出范围，应在 -200 到 200 之间")
                except ValueError:
                    print("输入无效，请输入一个数字")
                    
            elif cmd == 'f':
                try:
                    new_factor = float(input("请输入新的偏移因子 (0.0 到 1.0): "))
                    if 0.0 <= new_factor <= 1.0:
                        offset_factor = new_factor
                        print("偏移因子设置为: {:.1f}".format(offset_factor))
                    else:
                        print("偏移因子超出范围，应在 0.0 到 1.0 之间")
                except ValueError:
                    print("输入无效，请输入一个数字")
            
            elif cmd == 'p':
                print("当前速度 - 左轮: {:.2f}转/秒, 右轮: {:.2f}转/秒".format(lspeed, rspeed))
                if not record_data:
                    record_data = True
                    start_time = time.time()
                    time_data = []
                    left_speed_data = []
                    right_speed_data = []
                    left_pwm_data = []
                    right_pwm_data = []
                    print("开始记录数据...")
                else:
                    record_data = False
                    print("停止记录数据...")
                    # 绘制速度曲线
                    plt.figure(figsize=(10, 8))
                    plt.subplot(2, 1, 1)
                    plt.plot(time_data, left_speed_data, 'b-', label='左轮速度')
                    plt.plot(time_data, right_speed_data, 'r-', label='右轮速度')
                    plt.xlabel('时间 (秒)')
                    plt.ylabel('速度 (转/秒)')
                    plt.legend()
                    plt.title('电机速度曲线')
                    plt.grid(True)
                    
                    plt.subplot(2, 1, 2)
                    plt.plot(time_data, left_pwm_data, 'b--', label='左轮PWM')
                    plt.plot(time_data, right_pwm_data, 'r--', label='右轮PWM')
                    plt.xlabel('时间 (秒)')
                    plt.ylabel('PWM占空比 (%)')
                    plt.legend()
                    plt.title('PWM占空比曲线')
                    plt.grid(True)
                    
                    plt.tight_layout()
                    plt.savefig('motor_speed_curve.png')
                    plt.show()
                    
            else:
                print("未知命令: {}".format(cmd))
            
            # 短暂延时，避免CPU占用过高
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    finally:
        # 清理资源
        cleanup()
        print("资源已清理")