# detect_color.py
import cv2
import numpy as np
import json
import os
import threading
import time


# ===== 可配置参数（修改此处无需改动函数） =====
# 1. 截取的行范围（减少计算量）
DEFAULT_ROW_PERCENT = 0.25 # 默认在图片高度的50%位置取样，数字越小，取样行越高
DEFAULT_ROW_HEIGHT = 50     # 默认只处理一行

# 全局变量
camera = None
color_thread = None
is_running = False
latest_color_data = {}  # 存储最新的颜色检测结果

# ===== 初始化函数 =====
def init_camera(camera_id=0):
    """
    初始化摄像头
    
    Args:
        camera_id: 摄像头ID，默认为0（通常是内置摄像头）
    
    Returns:
        cv2.VideoCapture: 摄像头对象
    """
    global camera
    camera = cv2.VideoCapture(camera_id)
    
    # 检查摄像头是否成功打开
    if not camera.isOpened():
        print("错误: 无法打开摄像头")
        return None
    
    # 设置摄像头分辨率（可选）
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    print(f"摄像头已初始化: ID={camera_id}")
    return camera

# ===== 多线程颜色检测函数 =====
def color_detection_thread(interval=0.1):
    """
    持续运行的颜色检测线程
    
    Args:
        interval: 检测间隔时间（秒）
    """
    global camera, latest_color_data, is_running
    
    if camera is None:
        print("错误: 摄像头未初始化")
        return
    
    is_running = True
    print("颜色检测线程已启动")
    
    while is_running:
        # 读取一帧图像
        ret, frame = camera.read()
        if not ret:
            print("警告: 无法从摄像头读取图像")
            time.sleep(interval)
            continue
        
        # 调用颜色检测函数
        color_data = detect_color(frame)
        
        # 更新全局变量
        latest_color_data = color_data
        # 等待指定的间隔时间
        time.sleep(interval)

# 启动颜色检测线程
def start_color_detection(interval=0.1):
    """
    启动颜色检测线程
    
    Args:
        interval: 检测间隔时间（秒）
    
    Returns:
        threading.Thread: 线程对象
    """
    global color_thread, is_running
    
    # 如果线程已经在运行，先停止它
    if color_thread is not None and color_thread.is_alive():
        stop_color_detection()
    
    # 创建并启动新线程
    color_thread = threading.Thread(target=color_detection_thread, args=(interval,))
    color_thread.daemon = True  # 设为守护线程，主程序结束时自动结束
    color_thread.start()
    
    return color_thread

# 停止颜色检测线程
def stop_color_detection():
    """停止颜色检测线程"""
    global is_running, color_thread
    
    if color_thread is not None and color_thread.is_alive():
        is_running = False
        color_thread.join(timeout=1.0)  # 等待线程结束，最多等待1秒
        print("颜色检测线程已停止")

# 获取最新的颜色检测结果
def get_latest_color_data():
    """
    获取最新的颜色检测结果
    
    Returns:
        dict: 颜色位置字典，格式 {"color": [(x_start, x_end, x_center), ...]}
    """
    global latest_color_data
    return latest_color_data

# 清理函数
def cleanup():
    """释放摄像头资源"""
    global camera
    
    # 停止颜色检测线程
    stop_color_detection()
    
    # 释放摄像头
    if camera is not None:
        camera.release()
        camera = None
    
    # 关闭所有OpenCV窗口
    cv2.destroyAllWindows()
    print("摄像头资源已释放")

# 2. 从JSON文件加载颜色阈值
def load_color_ranges(json_path="hsv_thresholds.json"):
    """从JSON文件加载HSV颜色阈值"""
    # 获取当前文件所在目录的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 构建JSON文件的绝对路径
    json_path = os.path.join(current_dir, json_path)
    
    if not os.path.exists(json_path):
        print(f"警告: HSV阈值文件不存在: {json_path}")
        # 返回默认值
        return {
            "red":    ([np.array([0, 100, 100]), np.array([10, 255, 255])], 
                      [np.array([160, 100, 100]), np.array([179, 255, 255])]),
            "orange": ([np.array([11, 100, 100]), np.array([20, 255, 255])],),
            "yellow": ([np.array([21, 100, 100]), np.array([40, 255, 255])],),
            "green":  ([np.array([41, 100, 100]), np.array([80, 255, 255])],),
            "blue":   ([np.array([81, 100, 100]), np.array([130, 255, 255])],),
        }
    
    try:
        with open(json_path, 'r') as f:
            thresholds = json.load(f)
        
        except_colors = ["white","oranges"] # 需要排除的颜色名称

        # 转换JSON数据为OpenCV可用的格式
        color_ranges = {}
        for color, ranges in thresholds.items():
            if color in except_colors:
                continue
            color_range_list = []
            for range_dict in ranges:
                lower = np.array(range_dict["lower"])
                upper = np.array(range_dict["upper"])
                color_range_list.append((lower, upper))
            color_ranges[color] = tuple(color_range_list)
        
        print(f"已从 {json_path} 加载 {len(color_ranges)} 种颜色的阈值")
        return color_ranges
    
    except Exception as e:
        print(f"加载HSV阈值文件出错: {e}")
        # 出错时返回默认值
        return {
            "red":    ([np.array([0, 100, 100]), np.array([10, 255, 255])], 
                      [np.array([160, 100, 100]), np.array([179, 255, 255])]),
            "orange": ([np.array([11, 100, 100]), np.array([20, 255, 255])],),
            "yellow": ([np.array([21, 100, 100]), np.array([40, 255, 255])],),
            "green":  ([np.array([41, 100, 100]), np.array([80, 255, 255])],),
            "blue":   ([np.array([81, 100, 100]), np.array([130, 255, 255])],),
        }

# 加载颜色阈值
COLOR_RANGES = load_color_ranges()

dismiss_end = False

# ===== 核心函数 =====
def detect_color(frame):
    """
    检测指定行中的颜色分布
    Args:
        frame (np.ndarray): BGR格式的输入图像
    Returns:
        dict: 颜色位置字典，格式 {"color": [(x_start, x_end, x_center), ...]}
    """
    # 1. 根据图片高度动态计算截取的行范围
    height, width = frame.shape[:2]
    middle_row = int(height * DEFAULT_ROW_PERCENT)
    start_row = middle_row
    end_row = middle_row + DEFAULT_ROW_HEIGHT
    
    # 确保行范围在图片高度内
    start_row = max(0, min(start_row, height-1))
    end_row = max(start_row+1, min(end_row, height))
    
    # 截取行区域
    roi = frame[start_row:end_row, :]
    
    # 计算画面中心点
    center_x = width // 2

    # 2. 转换为HSV颜色空间
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # 3. 遍历颜色阈值，检测像素位置
    result = {}
    for color_name, ranges in COLOR_RANGES.items():
        # 合并多个颜色范围（如红色需要两个区间）
        mask = np.zeros((hsv.shape[0], hsv.shape[1]), dtype=np.uint8)
        for lower, upper in ranges:
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower, upper))

        # 找到符合颜色条件的x坐标
        x_coords = np.where(mask > 0)[1]
        if len(x_coords) == 0:
            continue  # 无该颜色像素，跳过
            
        # 处理离散点和空洞问题
        x_segments = process_color_segments(x_coords, width)
        
        if not x_segments:
            continue  # 处理后没有有效段，跳过
            
        # 如果有多个段，尝试合并间隔较小的段
        if len(x_segments) > 1:
            x_segments = merge_close_segments(x_segments)
            
        # 处理所有段，而不仅仅是最长的段
        segments_data = []
        for segment in x_segments:
            x_start, x_end = segment
            if dismiss_end and abs(x_start-x_end)<=0.1*width:
                print("忽略边缘")
                continue
            # 计算相对于中心的坐标
            x_start_rel = x_start - center_x
            x_end_rel = x_end - center_x
            x_center_rel = (x_start + x_end) // 2 - center_x
            
            segments_data.append((x_start_rel, x_end_rel, x_center_rel))
        
        # 将所有段数据添加到结果中
        result[color_name] = segments_data

    return result

def process_color_segments(x_coords, width):
    """
    处理颜色坐标，去除离散点，识别连续段
    Args:
        x_coords: 颜色像素的x坐标数组
        width: 图像宽度
    Returns:
        list: 有效颜色段列表，每个段为(start, end)元组
    """
    if len(x_coords) == 0:
        return []
        
    # 计算最小有效段长度（图像宽度的4%）
    min_segment_length = max(3, int(width * 0.04))
    
    # 排序坐标
    x_coords = np.sort(x_coords)
    
    # 找出不连续点的索引
    gaps = np.where(np.diff(x_coords) > 1)[0]
    
    # 分割成多个连续段
    segments = []
    start_idx = 0
    
    for gap_idx in gaps:
        end_idx = gap_idx + 1
        segment_start = x_coords[start_idx]
        segment_end = x_coords[gap_idx]
        
        # 只保留长度超过阈值的段
        if segment_end - segment_start >= min_segment_length:
            segments.append((segment_start, segment_end))
            
        start_idx = end_idx
    
    # 处理最后一段
    segment_start = x_coords[start_idx]
    segment_end = x_coords[-1]
    if segment_end - segment_start >= min_segment_length:
        segments.append((segment_start, segment_end))
    
    return segments

def merge_close_segments(segments):
    """
    合并间隔较小的颜色段
    Args:
        segments: 颜色段列表，每个段为(start, end)元组
    Returns:
        list: 合并后的颜色段列表
    """
    if len(segments) <= 1:
        return segments
        
    # 按起始位置排序
    segments.sort(key=lambda x: x[0])
    
    # 计算所有段的总长度
    total_length = sum(end - start for start, end in segments)
    
    # 计算最大允许的间隔（总长度的30%）
    max_gap = total_length * 0.3
    
    # 合并间隔小于阈值的段
    merged = []
    current_start, current_end = segments[0]
    
    for start, end in segments[1:]:
        # 如果当前段与上一段的间隔小于阈值，合并它们
        if start - current_end <= max_gap:
            current_end = end
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end
    
    # 添加最后一段
    merged.append((current_start, current_end))
    
    return merged


# 以下仅用于测试

# ===== 示例调用代码（摄像头实时检测） =====
if __name__ == "__main__":
    
    import glob

    def batch_test_images():
        """
        批量测试color_picture文件夹中的图片，并将结果保存到tested_color_picture文件夹
        """
        # 获取当前文件所在目录的绝对路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 构建输入和输出文件夹路径
        input_folder = os.path.join(current_dir, "color_picture")
        output_folder = os.path.join(current_dir, "tested_color_picture")
        
        # 确保输出文件夹存在
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"创建输出文件夹: {output_folder}")
        
        # 获取所有图片文件
        image_files = []
        for ext in ['jpg', 'jpeg', 'png', 'bmp']:
            image_files.extend(glob.glob(os.path.join(input_folder, f"*.{ext}")))
            image_files.extend(glob.glob(os.path.join(input_folder, f"*.{ext.upper()}")))
        
        if not image_files:
            print(f"警告: 在 {input_folder} 中未找到图片文件")
            return
        
        print(f"找到 {len(image_files)} 张图片，开始处理...")
        
        # 处理每张图片
        for img_path in image_files:
            # 读取图片
            frame = cv2.imread(img_path)
            if frame is None:
                print(f"无法读取图片: {img_path}")
                continue
            
            # 获取文件名（不含路径和扩展名）
            filename = os.path.basename(img_path)
            base_name, ext = os.path.splitext(filename)
            
            # 调用检测函数
            color_data = detect_color(frame)
            
            # 获取画面中心和中间行位置
            height, width = frame.shape[:2]
            center_x = width // 2
            middle_row = int(height * DEFAULT_ROW_PERCENT)
            
            # 在图像上绘制结果
            # 首先绘制中心参考线
            cv2.line(frame, (center_x, 0), (center_x, height), (255, 255, 255), 1)
            
            # 绘制水平检测线
            cv2.line(frame, (0, middle_row), (width, middle_row), (255, 255, 255), 1)
            
            # 在图像上方添加文件名和检测结果摘要
            colors_found = []
            for color, segments in color_data.items():
                colors_found.append(f"{color}({len(segments)})")
            
            result_text = f"File: {filename} | Colors: {', '.join(colors_found)}"
            cv2.putText(frame, result_text, (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            
            for color, segments in color_data.items():
                for i, (x1, x2, xc) in enumerate(segments):
                    # 将相对坐标转换回绝对坐标用于显示
                    abs_x1 = x1 + center_x
                    abs_x2 = x2 + center_x
                    abs_xc = xc + center_x
                    
                    # 绘制颜色区域和中心点
                    cv2.line(frame, (abs_x1, middle_row), (abs_x2, middle_row), (0, 255, 0), 2)
                    cv2.circle(frame, (abs_xc, middle_row), 5, (0, 0, 255), -1)
                    
                    # 显示颜色名称和相对位置（带正负号）
                    position_text = f"{color}_{i}: {xc:+d}"
                    cv2.putText(frame, position_text, (abs_xc-50, middle_row-20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            
            # 保存结果图片
            output_path = os.path.join(output_folder, f"{base_name}_result{ext}")
            cv2.imwrite(output_path, frame)
            print(f"已处理并保存: {output_path}")
        
        print(f"批量测试完成，结果已保存到: {output_folder}")


    # 选择运行模式
    mode = input("选择运行模式: 1=摄像头实时检测, 2=批量测试图片 [1/2]: ").strip()
    
    if mode == "2":
        batch_test_images()
    else:
        # 原有的摄像头检测代码
        cap = cv2.VideoCapture(0)
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # 调用检测函数
            color_data = detect_color(frame)
            
            # 获取画面中心和中间行位置
            height, width = frame.shape[:2]
            center_x = width // 2
            middle_row = int(height * DEFAULT_ROW_PERCENT)

            # 在图像上绘制结果（演示用）
            # 首先绘制中心参考线
            cv2.line(frame, (center_x, 0), (center_x, height), (255, 255, 255), 1)
            
            # 绘制水平检测线
            cv2.line(frame, (0, middle_row), (width, middle_row), (255, 255, 255), 1)
            
            # 获取并显示中心点的HSV值
            center_point = frame[middle_row, center_x]
            # 转换BGR到HSV
            hsv_frame = cv2.cvtColor(np.uint8([[center_point]]), cv2.COLOR_BGR2HSV)
            center_hsv = hsv_frame[0, 0]
            
            # 在画面上显示中心点HSV值
            hsv_text = f"中心HSV: {center_hsv[0]}, {center_hsv[1]}, {center_hsv[2]}"
            cv2.putText(frame, hsv_text, (center_x - 120, middle_row + 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # 在中心点绘制一个小方框，表示采样位置
            cv2.rectangle(frame, 
                         (center_x - 2, middle_row - 2), 
                         (center_x + 2, middle_row + 2), 
                         (0, 255, 255), 1)
            
            for color, segments in color_data.items():
                for i, (x1, x2, xc) in enumerate(segments):
                    # 将相对坐标转换回绝对坐标用于显示
                    abs_x1 = x1 + center_x
                    abs_x2 = x2 + center_x
                    abs_xc = xc + center_x
                    
                    # 绘制颜色区域和中心点
                    cv2.line(frame, (abs_x1, middle_row), (abs_x2, middle_row), (0, 255, 0), 2)
                    cv2.circle(frame, (abs_xc, middle_row), 5, (0, 0, 255), -1)
                    
                    # 显示颜色名称和相对位置（带正负号）
                    position_text = f"{color}_{i}: {xc:+d}"  # 添加段索引
                    cv2.putText(frame, position_text, (abs_xc-50, middle_row-20),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            cv2.imshow("Preview", frame)
            if cv2.waitKey(1) == 27:  # ESC退出
                break

        cap.release()
        cv2.destroyAllWindows()