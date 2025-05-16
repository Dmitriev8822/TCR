# Импорт необходимых компонентов SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, inspect
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime

from sec import CONNECTION_STRING  # Импорт пароля из защищенного файла

DEBUG_DB = False  # Флаг для отладки работы с БД

# Базовый класс для декларативного определения моделей
Base = declarative_base()


# Модель таблицы Cars (записи о проезжающих автомобилях)
class Cars(Base):
    __tablename__ = 'Cars'  # Имя таблицы в БД

    # Определение колонок таблицы:
    id = Column(Integer, primary_key=True, autoincrement=True)  # Первичный ключ
    plate = Column(String(9), nullable=False)  # Номерной знак (макс. 9 символов)
    direction = Column(String(25), nullable=False)  # Направление движения (въезд/выезд)
    time = Column(DateTime, nullable=False)  # Время проезда
    employee_id = Column(Integer, ForeignKey('Employees.employee_id'))  # Внешний ключ на сотрудника

    # Связь с таблицей Employees (один ко многим)
    employee = relationship("Employees", back_populates="cars")


# Модель таблицы Employees (информация о сотрудниках)
class Employees(Base):
    __tablename__ = 'Employees'

    # Определение колонок таблицы:
    employee_id = Column(Integer, primary_key=True, autoincrement=True)  # ID сотрудника
    name = Column(String(25), nullable=False)  # Имя сотрудника
    department = Column(String(50), nullable=False)  # Отдел/подразделение
    car_plate = Column(String(9), nullable=False)  # Номер автомобиля сотрудника

    # Связь с таблицей Cars (один ко многим)
    cars = relationship("Cars", back_populates="employee")


# Класс для работы с базой данных
class Database:
    def __init__(self, db_url=CONNECTION_STRING):
        """Инициализация подключения к базе данных"""
        self.db_url = db_url  # URL подключения к БД
        self.engine = create_engine(self.db_url)  # Создание движка SQLAlchemy
        self.Session = sessionmaker(bind=self.engine)  # Фабрика сессий
        self.session = self.Session()  # Текущая сессия
        self.create_tables()  # Создание таблиц, если их нет

    @staticmethod
    def log_DB(message):
        """Логирование действий с БД в файл"""
        if DEBUG_DB:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open('log_DB.txt', 'a') as file:
                file.write(current_time + ' ' + message + '\n')

    def create_tables(self):
        """Создание таблиц Cars и Employees, если они ещё не существуют"""
        inspector = inspect(self.engine)  # Инспектор для проверки существования таблиц
        existing_tables = inspector.get_table_names()  # Получаем список существующих таблиц

        # Создаем таблицу Employees, если её нет
        if "Employees" not in existing_tables:
            Base.metadata.tables['Employees'].create(self.engine)
            self.log_DB("Table 'Employees' was created")
        else:
            self.log_DB("Table 'Employees' already exists")

        # Создаем таблицу Cars, если её нет
        if "Cars" not in existing_tables:
            Base.metadata.tables['Cars'].create(self.engine)
            self.log_DB("Table 'Cars' was created")
        else:
            self.log_DB("Table 'Cars' already exists")

    def find_employee(self, plate):
        """Поиск сотрудника по автомобильному номеру"""
        # Ищем сотрудника с указанным номером автомобиля
        employee = self.session.query(Employees).filter_by(car_plate=plate).first()
        return employee.employee_id if employee else None  # Возвращаем ID или None если не найден

    def add_car(self, plate, direction):
        """Добавление новой записи в таблицу Cars"""
        # Сначала ищем сотрудника по номеру
        employee_id = self.find_employee(plate)

        # Создаем новую запись о проезде автомобиля
        new_car = Cars(
            plate=plate,
            direction=direction,
            time=datetime.now(),  # Текущее время
            employee_id=employee_id
        )

        # Добавляем и сохраняем
        self.session.add(new_car)
        self.session.commit()

        # Логируем действие
        status = "known" if employee_id else "unknown"
        self.log_DB(f'New car plate <{plate}> ({status}) was added')

    def add_employee(self, name, department, car_plate):
        """Добавление нового сотрудника в таблицу Employees"""
        # Создаем нового сотрудника
        new_employee = Employees(
            name=name,
            department=department,
            car_plate=car_plate
        )

        # Добавляем и сохраняем
        self.session.add(new_employee)
        self.session.commit()
        self.log_DB(f'New employee <{name}> was added')

    def get_all_cars(self):
        """Получение всех данных из таблицы Cars с информацией о сотрудниках"""
        # Выполняем запрос с объединением таблиц (LEFT JOIN)
        cars = self.session.query(
            Cars.plate,
            Employees.name,
            Employees.department,
            Cars.direction,
            Cars.time
        ).join(Employees, Cars.employee_id == Employees.employee_id, isouter=True).all()
        return cars

    def close(self):
        """Закрытие сессии с базой данных"""
        self.session.close()
        self.log_DB("Session was closed")