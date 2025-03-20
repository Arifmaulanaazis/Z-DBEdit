import warnings
warnings.simplefilter("ignore", DeprecationWarning)
import re
import telnetlib
import time
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QListWidget, QTableWidget,
                               QTableWidgetItem, QMessageBox, QHeaderView,
                               QProgressBar, QCompleter, QFileDialog)
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtCore import Qt, QObject, QThread, Signal, QStringListModel, QByteArray
from gambar import App_Icon
from datetime import datetime




class Worker(QObject):
    connected = Signal()
    connect_error = Signal(str)
    command_output = Signal(str, str)
    command_error = Signal(str, str)
    
    start_connect = Signal(str, str, str)
    start_command = Signal(str)
    start_disconnect = Signal()

    def __init__(self):
        super().__init__()
        self.tn = None
        
        self.start_connect.connect(self.connect_to_modem)
        self.start_command.connect(self.send_command)
        self.start_disconnect.connect(self.disconnect)

    def connect_to_modem(self, ip, user, password):
        try:
            self.tn = telnetlib.Telnet(ip)
            self.tn.read_until(b"Login: ")
            self.tn.write(user.encode('ascii') + b"\n")
            self.tn.read_until(b"Password: ")
            self.tn.write(password.encode('ascii') + b"\n")
            
            response = self.tn.read_until(b"^", timeout=2).decode('ascii')
            if "incorrect" in response.lower():
                raise ConnectionError("Login failed")
            
            self.connected.emit()
        except Exception as e:
            self.connect_error.emit(str(e))
            
    def send_command(self, command):
        try:
            if not self.tn:
                raise RuntimeError("Not connected to modem")
            
            self.tn.write(command.encode('ascii') + b"\n")
            time.sleep(0.5)
            output = b""
            while True:
                chunk = self.tn.read_very_eager()
                if not chunk:
                    break
                output += chunk
            output = output.decode('ascii')
            self.command_output.emit(command, output)
        except Exception as e:
            self.command_error.emit(command, str(e))

    def disconnect(self):
        if self.tn:
            self.tn.close()
            self.tn = None

class TelnetClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_table = None
        self.data_model = []
        self.modified_data = {}
        self.command_queue = []
        self.all_tables = []
        self.current_theme = 'dark'
        self.current_version = '1.0.0'
        
        self.init_ui()
        self.set_stylesheet(self.current_theme)
        self.init_worker_thread()
        #self.setWindowIcon(QIcon("icon.png"))

        pixmap = QPixmap()
        byte_array = QByteArray.fromBase64(App_Icon.encode())
        pixmap.loadFromData(byte_array, "PNG")
        self.setWindowIcon(QIcon(pixmap))

    def init_worker_thread(self):
        self.worker = Worker()
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        
        self.worker.connected.connect(self.handle_connected)
        self.worker.connect_error.connect(self.handle_connect_error)
        self.worker.command_output.connect(self.handle_command_output)
        self.worker.command_error.connect(self.handle_command_error)
        
        self.thread.start()

    def init_ui(self):
        self.setWindowTitle(f"Z-DBEdit - ZTE Modem Database Editor V{self.current_version}")
        self.setGeometry(100, 100, 1200, 800)
        
        # Membuat Menu Bar
        menubar = self.menuBar()
        
        # Menu File
        file_menu = menubar.addMenu("&File")
        
        load_config_action = QAction("&Load Config", self)
        load_config_action.triggered.connect(self.load_config)
        file_menu.addAction(load_config_action)
        
        save_config_action = QAction("&Save Config", self)
        save_config_action.triggered.connect(self.save_config)
        file_menu.addAction(save_config_action)
        
        save_as_config_action = QAction("Save &As Config", self)
        save_as_config_action.triggered.connect(self.save_as_config)
        file_menu.addAction(save_as_config_action)
        
        save_changes_action = QAction("&Save Change", self)
        save_changes_action.triggered.connect(self.save_changes)
        file_menu.addAction(save_changes_action)
        
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Menu Settings
        settings_menu = menubar.addMenu("&Settings")
        
        auto_save_action = QAction("&Auto save IP, Username and password", self)
        auto_save_action.setCheckable(True)
        auto_save_action.triggered.connect(self.toggle_auto_save)
        settings_menu.addAction(auto_save_action)
        
        theme_action = QAction("&Change Theme", self)
        theme_action.triggered.connect(self.change_theme)
        settings_menu.addAction(theme_action)
        
        # Menu Help
        help_menu = menubar.addMenu("&Help")
        help_action = QAction("&Usage Guide", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)
        
        # Menu About
        about_menu = menubar.addMenu("&About")
        about_action = QAction("&About Z-DBEdit", self)
        about_action.triggered.connect(self.show_about)
        about_menu.addAction(about_action)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        h_layout = QHBoxLayout()

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        self.ip_input = QLineEdit("192.168.1.1")
        self.user_input = QLineEdit("root")
        self.pass_input = QLineEdit("Zte521")
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.initiate_connection)
        
        connection_form = QWidget()
        form_layout = QVBoxLayout(connection_form)
        form_layout.addWidget(QLabel("IP Address:"))
        form_layout.addWidget(self.ip_input)
        form_layout.addWidget(QLabel("Username:"))
        form_layout.addWidget(self.user_input)
        form_layout.addWidget(QLabel("Password:"))
        form_layout.addWidget(self.pass_input)
        form_layout.addWidget(self.connect_btn)

        self.tables_list = QListWidget()
        self.tables_list.itemClicked.connect(self.load_table_data)
        
        left_layout.addWidget(connection_form)
        left_layout.addWidget(QLabel("Available Tables:"))
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tables...")
        left_layout.addWidget(self.search_input)
        
        self.completer_model = QStringListModel()
        self.completer = QCompleter()
        self.completer.setModel(self.completer_model)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.search_input.setCompleter(self.completer)
        
        self.search_input.textChanged.connect(self.filter_tables)
        
        left_layout.addWidget(self.tables_list)
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        self.current_table_label = QLabel("Selected Table: None")
        right_layout.addWidget(self.current_table_label)
        
        self.table_widget = QTableWidget()
        self.table_widget.itemChanged.connect(self.handle_item_changed)
        self.table_widget.setEditTriggers(QTableWidget.DoubleClicked)
        right_layout.addWidget(self.table_widget)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        h_layout.addWidget(left_panel, 1)
        h_layout.addWidget(right_panel, 3)
        
        main_layout.addLayout(h_layout)
        main_layout.addWidget(self.progress_bar)


    def set_stylesheet(self, theme='dark'):
        if theme == 'dark':
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #2b2b2b;
                }
                QWidget {
                    color: #ffffff;
                    font-size: 12px;
                }
                QLineEdit, QListWidget, QTableWidget {
                    background-color: #3c3f41;
                    border: 1px solid #555555;
                    padding: 5px;
                    border-radius: 3px;
                }
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QHeaderView::section {
                    background-color: #404244;
                    padding: 4px;
                }
                QProgressBar {
                    background-color: #3c3f41;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    text-align: center;
                    height: 15px;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    width: 10px;
                }

                QMenuBar {
                    background-color: #2b2b2b;
                    color: white;
                }
                QMenuBar::item:selected {
                    background-color: #3c3f41;
                }
                QMenu {
                    background-color: #3c3f41;
                    border: 1px solid #555555;
                }
                QMenu::item:selected {
                    background-color: #4CAF50;
                    color: white;
                }

                QMessageBox {
                    background-color: #2b2b2b;
                    color: white;
                    border: 1px solid #555555;
                }
            """)

        elif theme == 'light':
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #f5f5f5;
                }
                QWidget {
                    color: #333333;
                    font-size: 12px;
                }
                QLineEdit, QListWidget, QTableWidget {
                    background-color: #ffffff;
                    border: 1px solid #cccccc;
                    padding: 5px;
                    border-radius: 3px;
                }
                QPushButton {
                    background-color: #008CBA;
                    color: white;
                    border: none;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #007bb5;
                }
                QHeaderView::section {
                    background-color: #e0e0e0;
                    padding: 4px;
                    border: 1px solid #d0d0d0;
                }
                QProgressBar {
                    background-color: #ffffff;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                    text-align: center;
                    height: 15px;
                }
                QProgressBar::chunk {
                    background-color: #008CBA;
                    width: 10px;
                }

                QMenuBar {
                    background-color: #f5f5f5;
                    color: #333333;
                }
                QMenuBar::item:selected {
                    background-color: #e0e0e0;
                }
                QMenu {
                    background-color: #ffffff;
                    border: 1px solid #cccccc;
                }
                QMenu::item:selected {
                    background-color: #d0d0d0;
                    color: black;
                }

                QMessageBox {
                    background-color: #ffffff;
                    color: black;
                    border: 1px solid #cccccc;
                }
            """)


    # Fungsi untuk menu File
    def load_config(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Load Config", "", "Config Files (*.cfg);;All Files (*)"
        )
        if file_name:
            try:
                with open(file_name, 'r') as f:
                    data = f.read().splitlines()
                    if len(data) >= 3:
                        self.ip_input.setText(data[0])
                        self.user_input.setText(data[1])
                        self.pass_input.setText(data[2])
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load config: {str(e)}")

    def save_config(self):
        self._save_config_logic()

    def save_as_config(self):
        self._save_config_logic(save_as=True)

    def _save_config_logic(self, save_as=False):
        file_name = ""
        if not save_as:
            file_name = "default.cfg"
        else:
            file_name, _ = QFileDialog.getSaveFileName(
                self, "Save Config", "", "Config Files (*.cfg);;All Files (*)"
            )
        
        if file_name:
            try:
                with open(file_name, 'w') as f:
                    f.write(f"{self.ip_input.text()}\n")
                    f.write(f"{self.user_input.text()}\n")
                    f.write(f"{self.pass_input.text()}\n")
                QMessageBox.information(self, "Success", "Config saved successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save config: {str(e)}")

    # Fungsi untuk menu Settings
    def toggle_auto_save(self, checked):
        QMessageBox.information(self, "Info", f"Auto save feature {'enabled' if checked else 'disabled'}")

    def change_theme(self):
        self.current_theme = 'light' if self.current_theme == 'dark' else 'dark'
        if self.current_theme == 'light':
            self.set_stylesheet('light')
        else:
            self.set_stylesheet('dark')

    # Fungsi untuk menu Help dan About
    def show_help(self):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("Help")
        
        # Format Base64 sebagai data URI untuk HTML
        icon_base64_html = f'<img src="data:image/png;base64,{App_Icon}" width="32" height="32">'
        
        msg_box.setText(f"""
            <div style="text-align: center;">
                <img src="data:image/png;base64,{App_Icon}" width="100" height="100">
                <h2>Help and Instructions</h2>
            </div>
            <p><b>Z-DBEdit</b> is a GUI tool for managing database configurations on ZTE modems via Telnet.</p>
            
            <h3>Features:</h3>
            <ul>
                <li>Connect to ZTE modem via Telnet</li>
                <li>Retrieve and edit database tables</li>
                <li>Save and apply configuration changes</li>
                <li>Auto-save login credentials (optional)</li>
                <li>Dark mode support</li>
            </ul>
            
            <h3>How to Use:</h3>
            <ol>
                <li>Enter the modem's IP address, username, and password.</li>
                <li>Click the <b>Connect</b> button.</li>
                <li>Select a table from the list to view its data.</li>
                <li>Edit table values directly.</li>
                <li>Click <b>File</b> => <b>Save Change</b> to apply modifications.</li>
            </ol>
            
            <p>For more details, visit the <a href="https://github.com/Arifmaulanaazis/Z-DBEdit">GitHub Repository</a></p>
            
            <p><b>Version:</b> {self.current_version}</p>
            <p>© {datetime.now().year} Arif Maulana Azis</p>
        """)
        msg_box.exec()

    def show_about(self):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("About")
        
        icon_base64_html = f'<img src="data:image/png;base64,{App_Icon}" width="32" height="32">'
        
        msg_box.setText(f"""
            <div style="text-align: center;">
                <img src="data:image/png;base64,{App_Icon}" width="100" height="100">
                <h2>About Z-DBEdit</h2>
            </div>
            <p><b>Z-DBEdit</b> is a database editing tool designed for ZTE modems using Telnet.</p>
            <p>Developed by <b>Arif Maulana Azis</b></p>
            
            <p><b>Version:</b> {self.current_version}</p>
            <p>© {datetime.now().year} Arif Maulana Azis</p>
        """)
        msg_box.exec()

    def initiate_connection(self):
        ip = self.ip_input.text()
        user = self.user_input.text()
        password = self.pass_input.text()
        self.connect_btn.setEnabled(False)
        self.worker.start_connect.emit(ip, user, password)

    def handle_connected(self):
        self.connect_btn.setEnabled(True)
        QMessageBox.information(self, "Success", "Connected successfully!")
        self.worker.start_command.emit("sendcmd 1 DB all")

    def handle_connect_error(self, error):
        self.connect_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Connection failed: {error}")

    def handle_command_output(self, command, output):
        if command == "sendcmd 1 DB all":
            tables = re.findall(r"\d+\s+(\S+)", output)
            self.all_tables = tables
            self.completer_model.setStringList(tables)
            self.tables_list.clear()
            self.tables_list.addItems(tables)
        elif command.startswith("sendcmd 1 DB p"):
            self.parse_table_data(output)
        elif command.startswith("sendcmd 1 DB set"):
            self.worker.start_command.emit("sendcmd 1 DB save")
        elif command == "sendcmd 1 DB save":
            self.progress_bar.setValue(self.progress_bar.value() + 1)
            self.process_next_modification()

    def filter_tables(self, text):
        filtered = [table for table in self.all_tables 
                   if text.lower() in table.lower()]
        self.tables_list.clear()
        self.tables_list.addItems(filtered)

    def handle_command_error(self, command, error):
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Error", f"Command '{command}' failed: {error}")
        if self.command_queue:
            self.command_queue = []
            self.modified_data.clear()

    def load_table_data(self, item):
        self.current_table = item.text()
        self.current_table_label.setText(f"Selected Table: {self.current_table}")
        self.worker.start_command.emit(f"sendcmd 1 DB p {self.current_table}")

    def parse_table_data(self, output):
        rows = re.findall(r'<Row No="(\d+)">(.*?)</Row>', output, re.DOTALL)
        columns = set()
        self.data_model = []
        
        if not rows or (len(rows) == 1 and rows[0][0] == "0" and not rows[0][1].strip()):
            self.table_widget.clear()
            self.table_widget.setRowCount(1)
            self.table_widget.setColumnCount(1)
            self.table_widget.setHorizontalHeaderLabels(["Pesan"])
            item = QTableWidgetItem("There is no data in this table")
            item.setTextAlignment(Qt.AlignCenter)
            self.table_widget.setItem(0, 0, item)
            return

        for row in rows:
            row_data = {}
            fields = re.findall(r'<DM name="(.*?)" val="(.*?)"', row[1])
            for field in fields:
                row_data[field[0]] = field[1]
                columns.add(field[0])
            self.data_model.append(row_data)

        columns = sorted(columns)
        self.table_widget.clear()
        self.table_widget.setRowCount(len(self.data_model))
        self.table_widget.setColumnCount(len(columns))
        self.table_widget.setHorizontalHeaderLabels(columns)

        for row_idx, row_data in enumerate(self.data_model):
            for col_idx, col_name in enumerate(columns):
                item = QTableWidgetItem(row_data.get(col_name, ""))
                item.setData(Qt.UserRole, (row_idx, col_name))
                self.table_widget.setItem(row_idx, col_idx, item)

        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def handle_item_changed(self, item):
        if not item or not item.data(Qt.UserRole):
            return
        row_idx, col_name = item.data(Qt.UserRole)
        original_value = self.data_model[row_idx].get(col_name, "")
        if item.text() != original_value:
            self.modified_data[(row_idx, col_name)] = item.text()
        else:
            self.modified_data.pop((row_idx, col_name), None)

    def save_changes(self):
        if not self.modified_data:
            QMessageBox.warning(self, "Warning", "No changes to save")
            return
        
        self.modifications_queue = list(
            ((row_idx, col_name, new_value) for (row_idx, col_name), new_value in self.modified_data.items())
        )
        
        self.progress_bar.setMaximum(len(self.modifications_queue))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.process_next_modification()

    def process_next_modification(self):
        if self.modifications_queue:
            row_idx, col_name, new_value = self.modifications_queue.pop(0)
            row_id = self.data_model[row_idx].get("ViewName", "")
            if not row_id:
                self.process_next_modification()
                return
            cmd_set = f'sendcmd 1 DB set {self.current_table} {row_idx} {col_name} "{new_value}"'
            self.worker.start_command.emit(cmd_set)
        else:
            self.progress_bar.setVisible(False)
            QMessageBox.information(self, "Success", "Changes saved successfully!")
            self.modified_data.clear()
            if self.current_table:
                self.worker.start_command.emit(f"sendcmd 1 DB p {self.current_table}")

    def process_next_command(self):
        if self.command_queue:
            cmd = self.command_queue.pop(0)
            self.progress_bar.setValue(self.progress_bar.value() + 1)
            self.worker.start_command.emit(cmd)
        else:
            self.progress_bar.setVisible(False)
            QMessageBox.information(self, "Success", "Changes saved successfully!")
            self.modified_data.clear()
            if self.current_table:
                self.worker.start_command.emit(f"sendcmd 1 DB p {self.current_table}")

    def closeEvent(self, event):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Question)
        msg.setWindowTitle("Exit Confirmation")
        msg.setText("Are you sure you want to exit?")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        response = msg.exec()
        
        if response == QMessageBox.Yes:
            self.worker.start_disconnect.emit()
            self.thread.quit()
            self.thread.wait()
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QApplication([])
    window = TelnetClient()
    window.show()
    app.exec()