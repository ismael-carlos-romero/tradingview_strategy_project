@echo off
cd /d "C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project"
git add -A
git commit -m "Backup pre-RiskEngine/PositionManager: snapshot antes de refactor de risk management"
git log -1 --oneline
