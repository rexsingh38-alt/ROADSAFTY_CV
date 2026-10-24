@echo off
title SafeRoad AI Website
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-website.ps1"
if errorlevel 1 pause
