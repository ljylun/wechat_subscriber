#!/usr/bin/env python3
"""
微信公众号文章自动订阅系统 - 主入口
Main Entry Point
"""

import os
import sys
import argparse
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.scheduler import main as scheduler_main

if __name__ == '__main__':
    sys.exit(scheduler_main())
