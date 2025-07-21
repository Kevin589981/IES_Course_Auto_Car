# calibrate_hsv.py
import os
import cv2
import json
import numpy as np
from glob import glob

# 全局变量
roi = None
hsv_ranges = {}

roi = None
hsv_ranges = {}
scale_factor = 1.0  # 图像缩放比例

def select_roi(event, x, y, flags, param):
    """鼠标回调函数：选择ROI区域（坐标已缩放）"""
    global roi
    # 将窗口坐标转换为原始图像坐标
    x_orig = int(x / scale_factor)
    y_orig = int(y / scale_factor)
    
    if event == cv2.EVENT_LBUTTONDOWN:
        roi = (x_orig, y_orig, 10, 10)
    elif event == cv2.EVENT_MOUSEMOVE and flags == cv2.EVENT_FLAG_LBUTTON:
        if roi is not None:
            roi = (roi[0], roi[1], x_orig - roi[0], y_orig - roi[1])
    elif event == cv2.EVENT_LBUTTONUP:
        if roi is not None:
            x_start = min(roi[0], x_orig)
            y_start = min(roi[1], y_orig)
            w = abs(x_orig - roi[0])
            h = abs(y_orig - roi[1])
            roi = (x_start, y_start, w, h)
def load_existing_thresholds(json_path):
    """加载已有的阈值文件"""
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            return json.load(f)
    return {}

def process_image(image_path, json_path):
    """处理单张图片并保存阈值"""
    global hsv_ranges, scale_factor
    
    # 忽略 libpng 警告
    original_stderr = os.dup(2)  # 保存原始的标准错误输出
    null_fd = os.open(os.devnull, os.O_WRONLY)  # 创建空设备文件描述符
    os.dup2(null_fd, 2)  # 将标准错误重定向到空设备
    
    try:
        image = cv2.imread(image_path)
    finally:
        os.dup2(original_stderr, 2)  # 恢复标准错误输出
        os.close(null_fd)  # 关闭空设备文件描述符
    
    if image is None:
        print(f"无法读取图片: {image_path}")
        return
    
    # 获取屏幕分辨率
    screen_width = 1280  # 默认值，可以根据实际情况调整
    screen_height = 720
    
    # 计算缩放比例，确保图片能完全显示
    h, w = image.shape[:2]
    scale_w = screen_width * 0.8 / w
    scale_h = screen_height * 0.8 / h
    scale_factor = min(scale_w, scale_h, 1.0)  # 取最小值，且不超过1.0
    
    # 缩放图片用于显示
    display_width = int(w * scale_factor)
    display_height = int(h * scale_factor)
    
    # 创建可调整大小的窗口
    cv2.namedWindow("Calibrate HSV", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Calibrate HSV", display_width, display_height)
    cv2.setMouseCallback("Calibrate HSV", select_roi)
    
    while True:
        display = image.copy()
        if roi is not None and roi[2] > 0 and roi[3] > 0:
            x, y, w, h = roi
            cv2.rectangle(display, (x, y), (x + w, y + h), (0, 255, 0), 2)
            
            roi_image = image[y:y+h, x:x+w]
            hsv_roi = cv2.cvtColor(roi_image, cv2.COLOR_BGR2HSV)
            h_min, s_min, v_min = hsv_roi.min(axis=(0, 1))
            h_max, s_max, v_max = hsv_roi.max(axis=(0, 1))
            
            text = f"H: [{h_min}-{h_max}], S: [{s_min}-{s_max}], V: [{v_min}-{v_max}]"
            cv2.putText(display, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 2)
        
        # 缩放图片用于显示
        display_resized = cv2.resize(display, (display_width, display_height))
        cv2.imshow("Calibrate HSV", display_resized)
        key = cv2.waitKey(1)
        
        if key == ord('s'):
            # 使用控制台输入而不是GUI输入
            print("\n请在控制台输入颜色名称")
            color_name = input("输入颜色名称（如 'red'）: ").strip().lower()
            
            # 如果颜色已存在，询问是否追加或覆盖
            if color_name in hsv_ranges:
                print(f"颜色 '{color_name}' 已存在")
                action = input(f"追加(a) / 覆盖(o) / 取消(c)? ").lower()
                if action == 'a':
                    new_range = {
                        "lower": [int(h_min), int(s_min), int(v_min)],
                        "upper": [int(h_max), int(s_max), int(v_max)]
                    }
                    hsv_ranges[color_name].append(new_range)
                elif action == 'o':
                    hsv_ranges[color_name] = [{
                        "lower": [int(h_min), int(s_min), int(v_min)],
                        "upper": [int(h_max), int(s_max), int(v_max)]
                    }]
                else:
                    print("取消保存")
            else:
                hsv_ranges[color_name] = [{
                    "lower": [int(h_min), int(s_min), int(v_min)],
                    "upper": [int(h_max), int(s_max), int(v_max)]
                }]
            print(f"已保存 {color_name} 的阈值！")
        elif key == ord('q'):
            # 保存到JSON文件
            existing_data = load_existing_thresholds(json_path)
            for color, ranges in hsv_ranges.items():
                if color in existing_data:
                    existing_data[color].extend(ranges)
                else:
                    existing_data[color] = ranges
            with open(json_path, 'w') as f:
                json.dump(existing_data, f, indent=4)
            print(f"阈值已保存到 {json_path}")
            break
    
    cv2.destroyAllWindows()

def main():
    global scale_factor
    # 配置路径
    image_folder = r"D:\1\desktop\IES_project\color_picture" #input("请输入图片文件夹路径: ").strip()
    json_path = "hsv_thresholds.json"
    
    # 加载已有阈值
    global hsv_ranges
    hsv_ranges = load_existing_thresholds(json_path)
    
    # 遍历文件夹中的所有图片
    image_files = glob(os.path.join(image_folder, '*.jpg')) + \
                  glob(os.path.join(image_folder, '*.png'))
    
    for image_file in image_files:
        print(f"处理图片: {os.path.basename(image_file)}")
        process_image(image_file, json_path)
        hsv_ranges = load_existing_thresholds(json_path)  # 重新加载更新后的数据

if __name__ == "__main__":
    main()