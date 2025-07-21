import json
import os
import numpy as np

def is_overlapping(range1, range2):
    """判断两个HSV范围是否重叠"""
    # 检查每个通道是否有重叠
    h_overlap = max(range1["lower"][0], range2["lower"][0]) <= min(range1["upper"][0], range2["upper"][0])
    s_overlap = max(range1["lower"][1], range2["lower"][1]) <= min(range1["upper"][1], range2["upper"][1])
    v_overlap = max(range1["lower"][2], range2["lower"][2]) <= min(range1["upper"][2], range2["upper"][2])
    
    # 所有通道都重叠才算重叠
    return h_overlap and s_overlap and v_overlap

def merge_ranges(range1, range2):
    """合并两个重叠的HSV范围"""
    merged = {
        "lower": [
            min(range1["lower"][0], range2["lower"][0]),
            min(range1["lower"][1], range2["lower"][1]),
            min(range1["lower"][2], range2["lower"][2])
        ],
        "upper": [
            max(range1["upper"][0], range2["upper"][0]),
            max(range1["upper"][1], range2["upper"][1]),
            max(range1["upper"][2], range2["upper"][2])
        ]
    }
    return merged

def merge_hsv_thresholds(json_path):
    """合并HSV阈值文件中相交的颜色区域"""
    # 加载JSON文件
    if not os.path.exists(json_path):
        print(f"文件不存在: {json_path}")
        return
    
    with open(json_path, 'r') as f:
        thresholds = json.load(f)
    
    # 备份原始文件
    backup_path = json_path + '.backup'
    with open(backup_path, 'w') as f:
        json.dump(thresholds, f, indent=4)
    print(f"已创建备份文件: {backup_path}")
    
    # 处理每种颜色
    merged_thresholds = {}
    for color, ranges in thresholds.items():
        print(f"处理颜色: {color}, 原始阈值数量: {len(ranges)}")
        
        # 去除完全相同的阈值
        unique_ranges = []
        for r in ranges:
            if r not in unique_ranges:
                unique_ranges.append(r)
        
        # 合并重叠的阈值
        merged_ranges = []
        while unique_ranges:
            current = unique_ranges.pop(0)
            merged = False
            
            i = 0
            while i < len(unique_ranges):
                if is_overlapping(current, unique_ranges[i]):
                    current = merge_ranges(current, unique_ranges[i])
                    unique_ranges.pop(i)
                    merged = True
                else:
                    i += 1
            
            # 检查是否可以与已合并的范围合并
            i = 0
            while i < len(merged_ranges):
                if is_overlapping(current, merged_ranges[i]):
                    current = merge_ranges(current, merged_ranges[i])
                    merged_ranges.pop(i)
                    merged = True
                else:
                    i += 1
            
            merged_ranges.append(current)
            
            # 如果有合并，重新检查所有范围
            if merged:
                unique_ranges = merged_ranges + unique_ranges
                merged_ranges = []
        
        merged_thresholds[color] = merged_ranges
        print(f"处理完成: {color}, 合并后阈值数量: {len(merged_ranges)}")
    
    # 保存合并后的阈值
    with open(json_path, 'w') as f:
        json.dump(merged_thresholds, f, indent=4)
    
    print(f"已保存合并后的阈值到: {json_path}")
    
    # 输出统计信息
    total_original = sum(len(ranges) for ranges in thresholds.values())
    total_merged = sum(len(ranges) for ranges in merged_thresholds.values())
    print(f"总计: 原始阈值数量: {total_original}, 合并后阈值数量: {total_merged}")
    print(f"减少了 {total_original - total_merged} 个重复或重叠的阈值")

if __name__ == "__main__":
    json_path = r"D:\1\desktop\IES_project\hsv_thresholds.json"
    merge_hsv_thresholds(json_path)