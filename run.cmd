@echo off

:: Переход в директорию, где находится .cmd файл
cd /d "%~dp0"

echo "Creating or activating virtual environment..."

:: Проверка наличия виртуального окружения
if not exist ".venv" (
    echo "Virtual environment not found. Creating a new one..."
    python -m venv .venv
)

:: Активируем виртуальное окружение
call .venv\Scripts\activate

echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo "Running the main application..."
python main.py

:: Ожидание завершения, чтобы окно не закрывалось сразу
pause
