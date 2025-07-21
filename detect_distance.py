# detect_distance.py
import wiringpi as wpi
import threading
import time
import os
from collections import deque

# ===== 可配置参数（修改此处无需改动函数） =====
# 1. I2C设备地址和命令
DEFAULT_I2C_ADDRESS = 0x74  # KS103超声波传感器的I2C地址
DEFAULT_WRITE_CMD = 0xb0    # 测量范围0-5m，返回距离(mm)
# DEFAULT_READ_CMD = 0xb2  # 测量范围0-5m，返回飞行时间(us)，记得除以2

# 2. 测量参数
DEFAULT_MEASURE_INTERVAL = 0.1  # 默认测量间隔，单位秒
DEFAULT_DELAY_MS = 100          # 发送命令后的延迟时间，单位毫秒（最小约33ms）

# 3. 距离阈值（可根据实际情况调整）
MIN_DISTANCE_CM = 20.0  # 最小安全距离，单位厘米
MAX_DISTANCE_CM = 500.0  # 最大有效距离，单位厘米
MAX_DEVIATION = 40.0  # 最大允许偏差cm


# 全局变量
i2c_handle = None
distance_thread = None
is_running = False
latest_distance = -1.0  # 存储最新的距离测量结果，-1表示无效值
recent_distances = deque(maxlen=5)  # 存储最近5次有效的距离测量结果

# 线程锁，用于保护共享数据
distance_lock = threading.Lock()

# ===== 初始化函数 =====
def init_i2c(address=DEFAULT_I2C_ADDRESS):
    """
    初始化I2C设备
    
    Args:
        address: I2C设备地址，默认为0x74（KS103超声波传感器）
    
    Returns:
        int: I2C设备句柄，失败返回None
    """
    global i2c_handle
    
    try:
        # 打开I2C设备
        i2c_handle = wpi.wiringPiI2CSetup(address)
        if i2c_handle < 0:
            print(f"错误: 无法打开I2C设备，地址: 0x{address:02x}")
            return None
        
        print(f"I2C设备已初始化: 地址=0x{address:02x}, 句柄={i2c_handle}")
        return i2c_handle
    
    except Exception as e:
        print(f"初始化I2C设备出错: {e}")
        return None

# ===== 多线程距离测量函数 =====
def distance_measurement_thread(interval=DEFAULT_MEASURE_INTERVAL):
    """
    持续运行的距离测量线程
    
    Args:
        interval: 测量间隔时间（秒）
    """
    global i2c_handle, latest_distance, is_running, recent_distances
    
    if i2c_handle is None:
        print("错误: I2C设备未初始化")
        return
    
    is_running = True
    print("距离测量线程已启动")
    
    while is_running:
        try:
            # 测量距离
            distance = measure_distance()
            
            # 更新全局变量（使用线程锁保护）
            with distance_lock:
                # 检查测量值是否有效
                if distance >= 0:
                    # 检查是否需要进行异常值过滤
                    if len(recent_distances) >= 5:
                        # 计算最近5次测量的平均值
                        avg_distance = sum(recent_distances) / len(recent_distances)
                        
                        # 计算偏差百分比
                        if avg_distance > 0:  # 避免除以零
                            deviation = abs(distance - avg_distance)
                            recent_distances.append(distance)
                            # 如果偏差超过阈值，认为是测量错误
                            if deviation > MAX_DEVIATION:
                                print(f"测量异常: 当前值={distance:.1f}cm, 平均值={avg_distance:.1f}cm, 偏差={deviation:.1f}")
                            else:
                                # 更新最新距离和历史记录
                                latest_distance = distance
                                
                        else:
                            # 如果平均值为0，直接更新
                            latest_distance = distance
                            recent_distances.append(distance)
                    else:
                        # 历史记录不足5次，直接更新
                        latest_distance = distance
                        recent_distances.append(distance)
            
            # 等待指定的间隔时间
            time.sleep(interval)
            
        except Exception as e:
            print(f"距离测量出错: {e}")
            time.sleep(interval)  # 出错后仍然等待，避免频繁报错

# 启动距离测量线程
def start_distance_measurement(interval=DEFAULT_MEASURE_INTERVAL):
    """
    启动距离测量线程
    
    Args:
        interval: 测量间隔时间（秒）
    
    Returns:
        threading.Thread: 线程对象
    """
    global distance_thread, is_running
    
    # 如果线程已经在运行，先停止它
    if distance_thread is not None and distance_thread.is_alive():
        stop_distance_measurement()
    
    # 创建并启动新线程
    distance_thread = threading.Thread(target=distance_measurement_thread, args=(interval,))
    distance_thread.daemon = True  # 设为守护线程，主程序结束时自动结束
    distance_thread.start()
    
    return distance_thread

# 停止距离测量线程
def stop_distance_measurement():
    """停止距离测量线程"""
    global is_running, distance_thread
    
    if distance_thread is not None and distance_thread.is_alive():
        is_running = False
        distance_thread.join(timeout=1.0)  # 等待线程结束，最多等待1秒
        print("距离测量线程已停止")

# 获取最新的距离测量结果
def get_latest_distance():
    """
    获取最新的距离测量结果
    
    Returns:
        float: 距离值（厘米），如果无效则返回-1
    """
    global latest_distance
    
    # 使用线程锁保护读取操作
    with distance_lock:
        return latest_distance

# 清理函数
def cleanup():
    """释放I2C资源"""
    global i2c_handle
    
    # 停止距离测量线程
    stop_distance_measurement()
    
    # 释放I2C资源（wiringpi没有明确的关闭函数，但我们可以将句柄设为None）
    i2c_handle = None
    
    print("I2C资源已释放")

# ===== 核心函数 =====
def measure_distance(write_cmd=DEFAULT_WRITE_CMD, delay_ms=DEFAULT_DELAY_MS):
    """
    测量距离
    
    Args:
        write_cmd: 写入的命令，默认为0xb0（测量范围0-5m，返回距离）
        delay_ms: 发送命令后的延迟时间，单位毫秒
    
    Returns:
        float: 距离值（厘米），如果无效则返回-1
    """
    global i2c_handle
    
    if i2c_handle is None:
        print("错误: I2C设备未初始化")
        return -1
    
    try:
        # 发送测距命令
        wpi.wiringPiI2CWriteReg8(i2c_handle, 0x2, write_cmd)
        
        # 等待测量完成
        wpi.delay(delay_ms)  # 单位:毫秒，最小约33ms
        
        # 读取测量结果
        high_byte = wpi.wiringPiI2CReadReg8(i2c_handle, 0x2)
        low_byte = wpi.wiringPiI2CReadReg8(i2c_handle, 0x3)
        
        # 计算距离（单位：毫米）
        dist_mm = (high_byte << 8) + low_byte
        
        # 转换为厘米并返回
        dist_cm = dist_mm / 10.0
        
        # 检查距离是否在有效范围内
        if dist_cm < 0 or dist_cm > MAX_DISTANCE_CM:
            return -1  # 无效距离
        
        return dist_cm
    
    except Exception as e:
        print(f"测量距离出错: {e}")
        return -1

# 判断是否可能发生碰撞
def is_collision_possible(threshold_cm=MIN_DISTANCE_CM):
    """
    判断是否可能发生碰撞
    
    Args:
        threshold_cm: 碰撞阈值，单位厘米
    
    Returns:
        bool: 如果距离小于阈值，返回True；否则返回False
    """
    distance = get_latest_distance()
    
    # 如果距离无效或大于阈值，认为不会碰撞
    if distance < 0 or distance > threshold_cm:
        return False
    
    return True

# 以下仅用于测试

# ===== 示例调用代码（实时测距） =====
if __name__ == "__main__":
    try:
        # 初始化I2C设备
        if init_i2c() is None:
            print("初始化I2C设备失败，退出程序")
            exit(1)
        
        # 选择运行模式
        mode = input("选择运行模式: 1=单次测量, 2=连续测量 [1/2]: ").strip()
        
        if mode == "1":
            # 单次测量
            distance = measure_distance()
            if distance >= 0:
                print(f"距离: {distance:.1f} 厘米")
            else:
                print("测量失败或距离无效")
        else:
            # 连续测量
            print("开始连续测量（按Ctrl+C停止）...")
            print("如果距离小于最小安全距离，将显示警告")
            
            # 启动测量线程
            start_distance_measurement(interval=0.2)  # 每200ms测量一次
            
            try:
                while True:
                    # 获取最新距离
                    distance = get_latest_distance()
                    
                    if distance >= 0:
                        # 格式化输出距离
                        status = "正常"
                        if distance < MIN_DISTANCE_CM:
                            status = "警告: 可能发生碰撞！"
                        
                        print(f"\r距离: {distance:.1f} 厘米 - {status}", end="")
                    else:
                        print("\r测量失败或距离无效                ", end="")
                    
                    # 短暂暂停，避免频繁刷新终端
                    time.sleep(0.1)
            
            except KeyboardInterrupt:
                print("\n用户中断，停止测量")
            
            finally:
                # 停止测量线程
                stop_distance_measurement()
    
    except Exception as e:
        print(f"程序出错: {e}")
    
    finally:
        # 清理资源
        cleanup()
        print("程序结束")