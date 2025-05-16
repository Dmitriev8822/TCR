# Импорт необходимых библиотек
import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QDialogButtonBox, QMessageBox
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import QThread, pyqtSignal

import traceback  # Для обработки исключений

import cv2  # OpenCV для работы с видео
import sys
import queue  # Для организации очереди кадров
import time
import os

# Импорт пользовательских модулей
from YOLO.yolov8 import main as nn  # Нейронная сеть для распознавания номеров
from db import Database  # Модуль для работы с базой данных

FPS = 120  # Частота кадров для обработки
PATH_TO_IMG = os.path.join("DATA", "IMG")

# Функция для перехвата исключений
def excepthook(exc_type, exc_value, exc_tb):
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print("Oбнаружена ошибка !:", tb)
    QtWidgets.QApplication.quit()  # Завершение приложения при ошибке


# Установка перехватчика исключений
sys.excepthook = excepthook


# Класс для работы нейронной сети в отдельном потоке
class NnWorker(QThread):
    resultsReady = pyqtSignal(str)  # Сигнал с результатами распознавания

    def __init__(self):
        super().__init__()
        self.frame_queue = queue.Queue()  # Очередь кадров для обработки
        self.running = True  # Флаг работы потока

    def add_frame(self, frame):
        """Добавление кадра в очередь обработки"""
        self.frame_queue.put(frame)

    def clear_queue(self):
        """Очистка очереди кадров"""
        with self.frame_queue.mutex:
            self.frame_queue.queue.clear()

    def run(self):
        """Основной метод потока - обработка кадров из очереди"""
        while self.running:
            if not self.frame_queue.empty():
                print(f'Queue size: {self.frame_queue.qsize()}')
                frame = self.frame_queue.get()
                # Очищаем очередь, если она слишком большая
                if self.frame_queue.qsize() > 2:
                    self.clear_queue()

                # Получаем предсказания от нейронной сети
                predicts = nn(frame)
                print("Raw list", predicts)
                # Фильтруем только нормальные номера
                predicts = list(filter(self.isNormalPlate, predicts))
                # Сортируем по размеру (самый большой номер - первый)
                predicts.sort(key=lambda predict: -(predict[1][2] - predict[1][0]))
                print("After filter and sort list", predicts)
                predict = "Не распознан"
                if predicts != list():
                    predict = predicts[0][0]  # Берем первый (наиболее вероятный) номер

                self.resultsReady.emit(predict)  # Отправляем результат

    def isNormalPlate(self, predict: tuple) -> bool:
        """Проверка номера на соответствие шаблону"""
        import re
        plate = predict[0]
        # Шаблон для российских номеров: буква, 3 цифры, 2 буквы, 2-3 цифры
        pattern = r'^[A-Za-z]\d{3}[A-Za-z]{2}\d{2}\d?$'
        return bool(re.match(pattern, plate))

    def stop(self):
        """Остановка потока"""
        self.running = False
        self.quit()
        self.wait()


# Класс для захвата видео с камеры в отдельном потоке
class CameraThread(QThread):
    frameSignal = pyqtSignal(QImage)  # Сигнал с кадром для отображения

    def __init__(self, cameraIndex):
        super().__init__()
        # Инициализация видеозахвата
        self.cap = cv2.VideoCapture(cameraIndex)
        self.timer = QTimer()
        self.timer.timeout.connect(self.updateFrame)
        self.fps = 1000 // FPS  # Интервал таймера в мс
        self.timer.start(self.fps)

    def updateFrame(self):
        """Захват и обработка кадра с камеры"""
        ret, frame = self.cap.read()
        if ret:
            # Конвертация кадра в формат QImage для отображения
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
            self.frameSignal.emit(qt_image)  # Отправка кадра

    def stop(self):
        """Остановка потока"""
        self.timer.stop()
        self.cap.release()
        self.quit()
        self.wait()


# Основной класс для работы с камерой
class CameraUnit:
    def __init__(self, blockID, cameraIndex, videoLabel, plateOutLabel, cameraPosition):
        self.pos = cameraPosition  # Позиция камеры (вход/выход)

        self.blockID = blockID
        self.cameraIndex = cameraIndex
        self.videoLabel = videoLabel  # Label для отображения видео
        self.plateOutLabel = plateOutLabel  # Label для вывода номера
        self.frameCount = 0  # Счетчик кадров

        self.timeStart = int(time.time()) % 100
        self.countFPS = 0  # Счетчик FPS

        # Инициализация потока нейронной сети
        self.nnWorker = NnWorker()
        self.nnWorker.resultsReady.connect(self.handleNnResults)
        self.nnWorker.start()

        self.cameraTheard = None  # Поток камеры

        self.mostPopularPlate = None  # Самый частый номер в текущей сессии
        self.recPlates = list()  # Список распознанных номеров
        self.recPlatesCntEmpty = 0  # Счетчик пустых распознаваний

        self.testMode = False  # Режим тестирования

        # Инициализация базы данных
        self.db = None
        if not self.testMode:
            try:
                self.db = Database()
                self.create_tables()
            except Exception:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Critical)
                msg.setText("Error")
                msg.setInformativeText('Ошибка подключения к базе данных')
                msg.setWindowTitle("Error")
                msg.exec_()

    def create_tables(self):
        """Создание таблиц в БД при необходимости"""
        try:
            self.db.create_tables()
        except Exception:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setText("Error")
            msg.setInformativeText('Ошибка работы с базой данных')
            msg.setWindowTitle("Error")
            msg.exec_()

    def runCamera(self):
        """Запуск потока камеры"""
        self.cameraTheard = CameraThread(self.cameraIndex)
        self.cameraTheard.frameSignal.connect(self.updateFrame)
        self.cameraTheard.start()

    def countFrames(self) -> None:
        """Подсчет и вывод FPS"""
        if (int(time.time()) % 100) != self.timeStart:
            self.timeStart = int(time.time()) % 100
            print(f'FPS: {self.countFPS}')
            self.countFPS = 0
        self.countFPS += 1

    def updateFrame(self, image):
        """Обновление отображаемого кадра"""
        self.countFrames()
        frame = QPixmap.fromImage(image)
        self.videoLabel.setPixmap(frame)
        self.frameCount += 1

        # Обработка каждого 10-го кадра
        if self.frameCount % 10 == 0:
            self.processFrame(image)

    def processFrame(self, image):
        """Подготовка кадра для обработки нейронной сетью"""
        frame = image.convertToFormat(QImage.Format_RGB888)
        width = frame.width()
        height = frame.height()
        ptr = frame.bits()
        ptr.setsize(frame.byteCount())
        frame = np.array(ptr).reshape(height, width, 3)

        # Конвертация в формат OpenCV
        frame_cv2 = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # Добавление кадра в очередь обработки
        self.nnWorker.add_frame(frame_cv2)

    def handleNnResults(self, result: str) -> None:
        """Обработка результатов распознавания номера"""
        if result != "Номер не был распознан":
            self.recPlates.append(result)
            # Если накопилось достаточно номеров - определяем самый частый
            if len(self.recPlates) > 10:
                self.getMostPopularPlate()
                self.plateOutLabel.setText(self.mostPopularPlate)

    def getMostPopularPlate(self) -> None:
        """Определение самого частого номера"""
        # Увеличиваем вес текущего популярного номера
        if self.recPlates.count(self.mostPopularPlate) > 0:
            self.recPlates.extend([self.mostPopularPlate] * int(len(self.recPlates) * 0.5))

        # Поиск номера, который встречается в 60% случаев
        for plate in self.recPlates:
            lPlateCnt = self.recPlates.count(plate)
            if lPlateCnt >= int(len(self.recPlates) * 0.6):
                if self.mostPopularPlate != plate:
                    self.mostPopularPlate = plate
                    # Если номер новый и распознан - проверяем доступ
                    if (not self.testMode) and plate != "Не распознан" and self.checkAccess(plate):
                        self.db.add_car(plate, self.pos)  # Запись в БД
                        # команда на открытие шлагбаума / ворот

        self.recPlates = list()  # Очистка списка распознанных номеров

    def checkAccess(self, plate):
        """Проверка доступа автомобиля"""
        if self.db.find_employee(plate):  # Поиск в базе сотрудников
            return True

        # Запрос на пропуск неизвестного автомобиля
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Question)
        msg.setText(f"Автомобиль с номером <{plate}> не найден в базе данных сотрудников.\nПропустить автомобиль?")
        msg.setWindowTitle("Неизвестный автомобиль")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        retval = msg.exec_()

        return retval == QMessageBox.Ok

    def stopCamera(self):
        """Остановка всех потоков и очистка"""
        if self.cameraTheard is not None:
            self.cameraTheard.stop()
            self.cameraTheard = None

        if self.nnWorker is not None:
            self.nnWorker.clear_queue()
            self.nnWorker.stop()
            self.nnWorker = None

        if self.db:
            self.db.close()

        # Сброс интерфейса
        self.plateOutLabel.clear()
        self.plateOutLabel.setText('Номер')
        self.videoLabel.clear()

        # Установка заглушки вместо видео
        image_path = os.path.join(PATH_TO_IMG, "cameraPicS.jpg")
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.videoLabel.setPixmap(pixmap)
        else:
            self.videoLabel.setText("Не удалось загрузить изображение")