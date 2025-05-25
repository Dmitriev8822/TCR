# Импорт необходимых библиотек
import os.path

import numpy as np
from PyQt5 import uic, QtWidgets
from PyQt5.QtWidgets import (QMainWindow, QApplication, QFileDialog, QWidget, QTableWidgetItem,
                             QVBoxLayout, QLabel, QHBoxLayout, QComboBox, QMessageBox,
                             QFrame, QSpacerItem, QSizePolicy, QSplashScreen)
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPixmap, QImage, QFont
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import traceback
import cv2
import sys
import queue
import time
import os
from db import Database
from threads import CameraUnit, NnWorker

MAXBLOCKINDEX = 0
PATH_TO_UI = os.path.join("DATA", "UI")
PATH_TO_IMG = os.path.join("DATA", "IMG")

def excepthook(exc_type, exc_value, exc_tb):
    tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print("Oбнаружена ошибка !:", tb)
    QtWidgets.QApplication.quit()


sys.excepthook = excepthook


class LoadingScreen(QSplashScreen):
    def __init__(self):
        super().__init__()
        # Создаем загрузочный экран с сообщением
        self.setPixmap(QPixmap(os.path.join(PATH_TO_IMG, "logoLQ.png")))  # Можно использовать любое изображение
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        # Показываем загрузочный экран
        self.show()

        # Центрируем окно
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center() - self.rect().center())


class TableWindow(QWidget):
    def __init__(self):
        super().__init__()
        uic.loadUi(os.path.join(PATH_TO_UI, 'cars_table.ui'), self)

        self.db_manager = Database()
        self.data = self.db_manager.get_all_cars()

        self.tableWidget.setRowCount(len(self.data))
        self.tableWidget.setColumnCount(5)
        self.tableWidget.setHorizontalHeaderLabels(["Номерной знак", "Имя", "Отдел", "Направление", "Дата и время"])

        for row_index, row_data in enumerate(self.data):
            for col_index, value in enumerate(row_data):
                if value is None:
                    value = 'Информация отсутствует'
                item = QTableWidgetItem(str(value))
                self.tableWidget.setItem(row_index, col_index, item)

        self.destroyed.connect(self.db_manager.close)


class PhotoTestWin(QWidget):
    def __init__(self, image):
        super().__init__()
        uic.loadUi(os.path.join(PATH_TO_UI, 'test_window.ui'), self)

        frame = image

        height, width, channels = image.shape
        bytes_per_line = channels * width
        q_image = QImage(image.data, width, height, bytes_per_line, QImage.Format_RGB888)

        pixmap = QPixmap.fromImage(q_image)
        self.videoL_1.setPixmap(pixmap)

        self.nnWorker = NnWorker()
        self.nnWorker.resultsReady.connect(self.handleNnResults)
        self.nnWorker.add_frame(frame)
        self.nnWorker.start()

    def handleNnResults(self, plate: str):
        self.resultPlateOutL_1.setText(plate)
        self.nnWorker.clear_queue()
        self.nnWorker.stop()

    def processFrame(self, image):
        frame = image.convertToFormat(QImage.Format_RGB888)
        width = frame.width()
        height = frame.height()
        ptr = frame.bits()
        ptr.setsize(frame.byteCount())
        frame = np.array(ptr).reshape(height, width, 3)

        frame_cv2 = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        return frame_cv2


class Ui(QMainWindow):
    def __init__(self):
        super(Ui, self).__init__()
        self.loadUI()

    def loadUI(self):
        uic.loadUi(os.path.join(PATH_TO_UI, 'main.ui'), self)

        self.A_notes.triggered.connect(self.carsTable)
        self.A_photo.triggered.connect(self.openImage)
        self.A_video.triggered.connect(self.openVideo)
        self.A_add.triggered.connect(self.addCameraBlock)
        self.A_update.triggered.connect(self.fillAvailableCameras)
        self.A_delete.triggered.connect(self.deleteCameraBlock)

        self.activeCameraUnits = list()

        # Показываем основное окно после завершения загрузки
        self.show()

        # Создаем 2 блока камер по умолчанию
        for i in range(2):
            self.addCameraBlock()

    def addCameraBlock(self) -> None:
        global MAXBLOCKINDEX

        MAXBLOCKINDEX += 1

        cameraBlockWidget = QWidget()
        cameraBlockWidget.setObjectName(f'cameraBlock_{MAXBLOCKINDEX}')

        VL_cameraBlock = QVBoxLayout(cameraBlockWidget)

        HL_cameraPosition = QHBoxLayout()
        HL_cameraPosition.setObjectName(f'HL_cameraPosition_{MAXBLOCKINDEX}')

        HL_cameraIndex = QHBoxLayout()
        HL_cameraIndex.setObjectName(f'HL_cameraIndex_{MAXBLOCKINDEX}')

        L_cameraName = QLabel(f'Камера №{MAXBLOCKINDEX}')
        L_cameraName.setObjectName(f'L_cameraName_{MAXBLOCKINDEX}')
        L_cameraName.setAlignment(Qt.AlignCenter)
        L_cameraName.setFixedHeight(50)

        L_resultPlateOut = QLabel("Номер")
        L_resultPlateOut.setObjectName(f'L_resultPlateOut_{MAXBLOCKINDEX}')
        L_resultPlateOut.setAlignment(Qt.AlignCenter)
        L_resultPlateOut.setFixedHeight(50)

        L_videoOut = QLabel("Видео")
        L_videoOut.setObjectName(f'L_videoOut_{MAXBLOCKINDEX}')
        L_videoOut.setScaledContents(True)

        L_cameraPosition = QLabel("Расположение:")
        L_cameraPosition.setObjectName(f'L_cameraPosition_{MAXBLOCKINDEX}')
        L_cameraPosition.setAlignment(Qt.AlignLeft)

        L_cameraIndex = QLabel("Камера:")
        L_cameraIndex.setObjectName(f'L_cameraIndex_{MAXBLOCKINDEX}')
        L_cameraIndex.setAlignment(Qt.AlignLeft)

        CB_cameraPosition = QComboBox()
        CB_cameraPosition.setObjectName(f'CB_cameraPosition_{MAXBLOCKINDEX}')
        CB_cameraPosition.addItem('')
        CB_cameraPosition.addItem('Въезд')
        CB_cameraPosition.addItem('Выезд')

        CB_cameraIndex = QComboBox()
        CB_cameraIndex.setObjectName(f'CB_cameraIndex_{MAXBLOCKINDEX}')

        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        line2 = QFrame(self)
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)

        line3 = QFrame(self)
        line3.setFrameShape(QFrame.HLine)
        line3.setFrameShadow(QFrame.Sunken)

        line4 = QFrame(self)
        line4.setFrameShape(QFrame.HLine)
        line4.setFrameShadow(QFrame.Sunken)

        VL_cameraBlock.addWidget(L_cameraName, stretch=1)
        VL_cameraBlock.addWidget(line)
        VL_cameraBlock.addLayout(HL_cameraPosition, stretch=2)
        VL_cameraBlock.addWidget(line4)
        VL_cameraBlock.addLayout(HL_cameraIndex, stretch=2)
        VL_cameraBlock.addWidget(line2)
        VL_cameraBlock.addWidget(L_resultPlateOut, stretch=1)
        VL_cameraBlock.addWidget(line3)
        VL_cameraBlock.addWidget(L_videoOut, stretch=4)

        HL_cameraPosition.addWidget(L_cameraPosition)
        HL_cameraPosition.addWidget(CB_cameraPosition)

        HL_cameraIndex.addWidget(L_cameraIndex)
        HL_cameraIndex.addWidget(CB_cameraIndex)

        self.HL_mainLayout.addWidget(cameraBlockWidget)

        CB_cameraIndex.currentIndexChanged.connect(self.runCamera)

        cameraBlockWidget.setStyleSheet("""
            QWidget#cameraBlock_""" + str(MAXBLOCKINDEX) + """ {
                font-family: 'Open Sans';
                background-color: lightgray;
                border: 1px solid black;
                border-radius: 15px;
                padding: 10px;
            }
            QLabel#L_resultPlateOut_""" + str(MAXBLOCKINDEX) + """ {
                font-size: 16pt;
                font-style: bold;
            }
        """)

        image_path = os.path.join(PATH_TO_IMG, "cameraPicS.jpg")
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            L_videoOut.setPixmap(pixmap)
        else:
            L_videoOut.setText("Не удалось загрузить изображение")

    def deleteCameraBlock(self) -> None:
        global MAXBLOCKINDEX

        if MAXBLOCKINDEX == 0:
            return

        last_block = self.findChild(QWidget, f'cameraBlock_{MAXBLOCKINDEX}')

        if last_block is not None:
            self.HL_mainLayout.removeWidget(last_block)
            last_block.deleteLater()
            MAXBLOCKINDEX -= 1

    def carsTable(self):
        self.table_window = TableWindow()
        self.table_window.show()

    def runCamera(self) -> int:
        comboBox = self.sender()
        blockID = int(comboBox.objectName().split('_')[-1])

        for cameraUnit in self.activeCameraUnits:
            if cameraUnit.blockID == blockID:
                cameraUnit.stopCamera()
                self.activeCameraUnits.remove(cameraUnit)

        cameraIndex = comboBox.currentIndex() - 1

        if cameraIndex == -1:
            return -1

        videoLabel = self.findChild(QtWidgets.QLabel, f'L_videoOut_{blockID}')
        plateOutLabel = self.findChild(QtWidgets.QLabel, f'L_resultPlateOut_{blockID}')
        cameraPosition = self.findChild(QtWidgets.QComboBox, f'CB_cameraPosition_{blockID}').currentIndex()
        cameraPosition = ['Информация отсутствует', 'Въезд', 'Выезд'][cameraPosition]

        cameraUnit = CameraUnit(blockID, cameraIndex, videoLabel, plateOutLabel, cameraPosition)
        cameraUnit.runCamera()
        self.activeCameraUnits.append(cameraUnit)

        return 0

    def fillAvailableCameras(self) -> None:
        comboBoxes = [self.findChild(QtWidgets.QComboBox, f'CB_cameraIndex_{bi}') for bi in range(1, MAXBLOCKINDEX + 1)]
        for cameraBox in comboBoxes:
            cameraBox.clear()
            cameraBox.addItem("")

        availableCameras = self.getAvailableCameras()

        for cameraIndex in availableCameras:
            for cameraBox in comboBoxes:
                cameraBox.addItem("Камера " + str(cameraIndex))

    def getAvailableCameras(self, maxCameras=2) -> list:
        availableCameras = list()
        for index in range(maxCameras):
            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                availableCameras.append(index)
                cap.release()

        return availableCameras

    def openImage(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp)")
        if file_name:
            image = cv2.imread(file_name)
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            self.test_window = PhotoTestWin(image)
            self.test_window.show()

    def openVideo(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Все файлы (*.*)")
        print(file_path)
        vt = VideoTestWin(file_path)

def checkDBConnection():
    try:
        test_connetion = Database()
        test_connetion.close()
    except Exception as e:
        error_details = traceback.format_exc()
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setText("Error")
        msg.setInformativeText(f'Ошибка подключения к базе данных:\n{e}')
        msg.setDetailedText(error_details)
        msg.setWindowTitle("Error")
        msg.exec_()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    default_font = QFont("Open Sans", 14)
    app.setFont(default_font)

    splash_pix = QPixmap(os.path.join(PATH_TO_IMG, "logoLQ.png"))
    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.setMask(splash_pix.mask())
    splash.show()
    app.processEvents()

    # time.sleep(2)

    window = Ui()
    window.show()

    splash.finish(window)
    checkDBConnection()

    app.exec_()