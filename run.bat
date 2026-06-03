@echo off
chcp 65001 > nul
echo ====================================
echo  CAN Scheduling 分析程式
echo ====================================
python can_scheduling.py
echo.
echo 程式執行完畢，圖片已儲存在此資料夾。
pause
