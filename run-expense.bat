@echo off
REM =========================================================================
REM AGENTIC MONTHLY EXPENSE MANAGER - STARTUP
REM =========================================================================
REM Simply activates the virtual environment and runs the Streamlit app
REM =========================================================================

echo.
echo ========================================
echo   Agentic Monthly Expense Manager
echo ========================================
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Run Streamlit
streamlit run agent.py

pause
