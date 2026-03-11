# TelegramSupportBot

**Этот проект представляет собой легковесного Telegram-бота для анонимных ответов пользователям**

## Как работает

Пользователь пишет команду /start, после этого бот отправляет приветсвенное сообщение, после которого может написать свое обращение администраторам. У адимнистраторов под обращением появляется две кнопки "Ответить" и "Закрыть" 
___
## Что потребуется для бота?
Чтобы обеспечить корректную работу бота в файле **.env** требуется прописать токен, который выдает BotFather и ID Администраторов. ID можно увидеть в форках приложения Телеграмм или в ботах.  

### Что использует бот
Бот использует Python версии 3.14.0 и библиотеки aiogram и dotenv
___
## Установка бота
### Установка зависимостей для сборки Python
sudo apt update  
sudo apt install -y build-essential libssl-dev zlib1g-dev \  
libncurses5-dev libncursesw5-dev libreadline-dev libsqlite3-dev \  
libffi-dev libbz2-dev wget

### Скачиваем исходники Python 3.14.0
wget https://www.python.org/ftp/python/3.14.0/Python-3.14.0.tgz

### Распаковываем архив
tar -xvf Python-3.14.0.tgz  
cd Python-3.14.0

### Сборка и установка
./configure --enable-optimizations  
make -j$(nproc)  
sudo make altinstall

### Установка Screen 
sudo apt install -y screen
### Настройка бота
cd <расположение бота>  
nano .env

### Запуск бота
screen -S bot  
python3.14 main.py

**Теперь бот готов к использовнию** 