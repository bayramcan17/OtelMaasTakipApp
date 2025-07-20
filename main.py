import sys
import sqlite3
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QDialog, QLabel, QLineEdit, QFormLayout, QDateEdit, QTabWidget, QHeaderView, QGroupBox,
    QTableView, QAbstractItemView, QTableWidgetSelectionRange, QSystemTrayIcon, QStyle, QMenu, QAction,
    QMessageBox
)
from PyQt5.QtCore import Qt, QDate, QTimer
from PyQt5.QtGui import QIcon

# Global database connection
conn = sqlite3.connect("otel_maas.db")

def initialize_database():
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                salary REAL NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS advances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS salaries (
                employee_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                salary REAL NOT NULL,
                PRIMARY KEY (employee_id, year, month),
                FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
            )
        """)
        
        # Check if description column exists in advances table, if not add it
        try:
            cursor.execute("SELECT description FROM advances LIMIT 1")
        except sqlite3.OperationalError:
            # Column doesn't exist, add it
            cursor.execute("ALTER TABLE advances ADD COLUMN description TEXT")
            print("Added description column to advances table")
        
        conn.commit()
    except sqlite3.Error as e:
        QMessageBox.critical(None, "Veritabanı Hatası", 
                           f"Veritabanı başlatılırken hata oluştu:\n{str(e)}")
        sys.exit(1)
    except Exception as e:
        QMessageBox.critical(None, "Beklenmeyen Hata", 
                           f"Beklenmeyen bir hata oluştu:\n{str(e)}")
        sys.exit(1)


class Employee:
    def get_salary_for_month(self, month, year):
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT salary FROM salaries WHERE employee_id = ? AND year = ? AND month = ?
            """, (self.id, year, month))
            row = cursor.fetchone()
            if row is not None:
                return row[0]
            return self.salary
        except sqlite3.Error as e:
            QMessageBox.warning(None, "Veritabanı Hatası", 
                              f"Maaş bilgisi alınırken hata oluştu:\n{str(e)}")
            return self.salary
        except Exception as e:
            QMessageBox.warning(None, "Beklenmeyen Hata", 
                              f"Beklenmeyen bir hata oluştu:\n{str(e)}")
            return self.salary
    def __init__(self, id_, first_name, last_name, start_date, salary):
        self.id = id_
        self.first_name = first_name
        self.last_name = last_name
        self.start_date = start_date  # QDate
        self.salary = salary

    def advances_for_month(self, month, year=None):
        if year is None:
            year = QDate.currentDate().year()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, date, amount, description FROM advances 
                WHERE employee_id = ? AND strftime('%m', date) = ? AND strftime('%Y', date) = ?
                ORDER BY date
            """, (self.id, f"{month:02d}", str(year)))
            results = cursor.fetchall()
            advances = []
            for id_, date_str, amount, description in results:
                date = QDate.fromString(date_str, "yyyy-MM-dd")
                advances.append((id_, date, amount, description))
            return advances
        except sqlite3.Error as e:
            QMessageBox.warning(None, "Veritabanı Hatası", 
                              f"Avans bilgisi alınırken hata oluştu:\n{str(e)}")
            return []
        except Exception as e:
            QMessageBox.warning(None, "Beklenmeyen Hata", 
                              f"Beklenmeyen bir hata oluştu:\n{str(e)}")
            return []

    def total_advances_for_month(self, month, year=None):
        if year is None:
            year = QDate.currentDate().year()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT SUM(amount) FROM advances 
                WHERE employee_id = ? AND strftime('%m', date) = ? AND strftime('%Y', date) = ?
            """, (self.id, f"{month:02d}", str(year)))
            result = cursor.fetchone()[0]
            return result if result is not None else 0
        except sqlite3.Error as e:
            QMessageBox.warning(None, "Veritabanı Hatası", 
                              f"Toplam avans hesaplanırken hata oluştu:\n{str(e)}")
            return 0
        except Exception as e:
            QMessageBox.warning(None, "Beklenmeyen Hata", 
                              f"Beklenmeyen bir hata oluştu:\n{str(e)}")
            return 0

    def carried_salary_for_month(self, target_month):
        """
        Calculates the total carried salary for all months before target_month (1-based).
        Handles year boundaries for December start employees.
        """
        # Validate input
        if target_month < 1 or target_month > 12:
            return 0
            
        if target_month == self.start_date.month() and QDate.currentDate().year() == self.start_date.year():
            # No carried salary for the starting month in the starting year
            return 0
        
        cumulative_carry = 0
        start_month = self.start_date.month()
        start_year = self.start_date.year()
        current_year = QDate.currentDate().year()
        
        # Handle year boundaries
        if current_year == start_year:
            # Same year: only consider months from start month to target month
            for month in range(start_month, target_month):
                advances = self.total_advances_for_month(month, current_year)
                if month == self.start_date.month():
                    # For start month, use prorated salary
                    days_in_month = QDate(self.start_date.year(), month, 1).daysInMonth()
                    proportion = (days_in_month - self.start_date.day() + 1) / days_in_month
                    month_salary = self.get_salary_for_month(month, current_year) * proportion
                else:
                    # For other months, use full salary
                    month_salary = self.get_salary_for_month(month, current_year)
                remaining = month_salary - advances
                cumulative_carry += remaining
        else:
            # Different year: need to handle year boundary
            # First, calculate carried salary from previous year (start month to December)
            for month in range(start_month, 13):
                advances = self.total_advances_for_month(month, start_year)
                if month == self.start_date.month():
                    # For start month, use prorated salary
                    days_in_month = QDate(self.start_date.year(), month, 1).daysInMonth()
                    proportion = (days_in_month - self.start_date.day() + 1) / days_in_month
                    month_salary = self.get_salary_for_month(month, start_year) * proportion
                else:
                    # For other months, use full salary
                    month_salary = self.get_salary_for_month(month, start_year)
                remaining = month_salary - advances
                cumulative_carry += remaining
            
            # Then add carried salary from current year (January to target month - 1)
            for month in range(1, target_month):
                advances = self.total_advances_for_month(month, current_year)
                month_salary = self.get_salary_for_month(month, current_year)
                remaining = month_salary - advances
                cumulative_carry += remaining
        
        return cumulative_carry

    def remaining_salary_for_month(self, month):
        year = QDate.currentDate().year()
        total_advance = self.total_advances_for_month(month, year)

        # Check if this is the actual start month (both month and year must match)
        if month == self.start_date.month() and year == self.start_date.year():
            # Sadece orantılı maaş hesapla, taşınan maaş eklenmesin
            days_in_month = QDate(self.start_date.year(), month, 1).daysInMonth()
            proportion = (days_in_month - self.start_date.day() + 1) / days_in_month
            current_salary = self.get_salary_for_month(month, year)
            prorated_salary = current_salary * proportion
            return prorated_salary - total_advance

        # Diğer aylarda tam maaş + taşınan maaş
        current_salary = self.get_salary_for_month(month, year)
        carried = self.carried_salary_for_month(month)
        return carried + current_salary - total_advance


class AddEmployeeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yeni Çalışan Ekle")
        self.setModal(True)
        layout = QFormLayout()

        self.first_name_edit = QLineEdit()
        self.last_name_edit = QLineEdit()
        self.start_date_edit = QDateEdit(QDate.currentDate())
        self.start_date_edit.setCalendarPopup(True)
        self.salary_edit = QLineEdit()
        self.salary_edit.setPlaceholderText("Maaş (örn: 10000)")

        layout.addRow("Ad:", self.first_name_edit)
        layout.addRow("Soyad:", self.last_name_edit)
        layout.addRow("Başlama Tarihi:", self.start_date_edit)
        layout.addRow("Maaş:", self.salary_edit)

        button_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Ekle")
        self.cancel_btn = QPushButton("İptal")
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addRow(button_layout)

        self.setLayout(layout)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def get_employee_data(self):
        try:
            salary = float(self.salary_edit.text())
            if salary < 0:
                salary = 0
        except ValueError:
            salary = 0
        
        start_date = self.start_date_edit.date()
        current_date = QDate.currentDate()
        
        # Check if start date is in the future
        if start_date.toJulianDay() > current_date.toJulianDay():
            QMessageBox.warning(self, "Geçersiz Tarih", 
                              "Başlama tarihi bugünden sonra olamaz!\nLütfen geçerli bir tarih seçin.")
            return None, None, None, 0
        
        return (
            self.first_name_edit.text().strip(),
            self.last_name_edit.text().strip(),
            start_date,
            salary
        )


class AddAdvanceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Avans Ekle")
        self.setModal(True)
        layout = QFormLayout()

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("Tutar (örn: 1000)")
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("Açıklama (örn: Acil ihtiyaç)")

        layout.addRow("Tarih:", self.date_edit)
        layout.addRow("Tutar:", self.amount_edit)
        layout.addRow("Açıklama:", self.description_edit)

        button_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Ekle")
        self.cancel_btn = QPushButton("İptal")
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addRow(button_layout)

        self.setLayout(layout)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def get_advance_data(self):
        try:
            amount = float(self.amount_edit.text())
            if amount < 0:
                amount = 0
        except ValueError:
            amount = 0
        return (self.date_edit.date(), amount, self.description_edit.text().strip())


class EmployeeDetailDialog(QDialog):
    def __init__(self, employee: Employee, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Çalışan Detayı")
        self.employee = employee
        self.resize(500, 400)
        layout = QVBoxLayout()

        self.tabs = QTabWidget()
        self.start_month = self.employee.start_date.month()
        self.start_year = self.employee.start_date.year()
        self.current_year = QDate.currentDate().year()
        
        # Determine which months to show based on year
        if self.current_year == self.start_year:
            # First year: show from start month to December
            months_to_show = range(self.start_month, 13)
        else:
            # Subsequent years: show all 12 months
            months_to_show = range(1, 13)
        
        for month in months_to_show:
            self.tabs.addTab(self.create_month_tab(month), f"{month}. Ay")
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def create_month_tab(self, month):
        tab = QWidget()
        vbox = QVBoxLayout()

        # Info
        info_group = QGroupBox("Çalışan Bilgileri")
        info_layout = QFormLayout()
        info_layout.addRow("Ad:", QLabel(self.employee.first_name))
        info_layout.addRow("Soyad:", QLabel(self.employee.last_name))
        info_layout.addRow("Başlama Tarihi:", QLabel(self.employee.start_date.toString("dd.MM.yyyy")))
        current_salary = self.employee.get_salary_for_month(month, QDate.currentDate().year())
        info_layout.addRow("Maaş:", QLabel(f"{current_salary:.2f}"))
        info_group.setLayout(info_layout)
        vbox.addWidget(info_group)

        # Advances summary
        year = QDate.currentDate().year()
        current_salary = self.employee.get_salary_for_month(month, year)
        carried = self.employee.carried_salary_for_month(month)
        advances_sum = self.employee.total_advances_for_month(month)
        
        # Use the proper remaining salary calculation
        remaining = self.employee.remaining_salary_for_month(month)

        summary_group = QGroupBox("Avans Bilgisi")
        summary_layout = QFormLayout()
        summary_layout.addRow("Toplam Avans:", QLabel(f"{advances_sum:.2f}"))
        summary_layout.addRow("Kalan Maaş:", QLabel(f"{remaining:.2f}"))
        summary_group.setLayout(summary_layout)
        vbox.addWidget(summary_group)

        # Maaş güncelleme arayüzü
        salary_edit = QLineEdit()
        salary_edit.setPlaceholderText("Yeni maaş girin")
        salary_edit.setText(str(current_salary))
        update_salary_btn = QPushButton("Maaşı Güncelle")

        def update_salary():
            try:
                new_salary = float(salary_edit.text())
                if new_salary < 0:
                    QMessageBox.warning(self, "Geçersiz Değer", "Maaş negatif olamaz!")
                    return
            except ValueError:
                QMessageBox.warning(self, "Geçersiz Değer", "Lütfen geçerli bir sayı girin!")
                return
            
            try:
                # Use the appropriate year based on the current view
                year = QDate.currentDate().year()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO salaries (employee_id, year, month, salary)
                    VALUES (?, ?, ?, ?)
                """, (self.employee.id, year, month, new_salary))
                conn.commit()
                self.refresh_tab(month)
                QMessageBox.information(self, "Başarılı", f"{month}. ay {year} maaşı başarıyla güncellendi!")
            except sqlite3.Error as e:
                QMessageBox.critical(self, "Veritabanı Hatası", 
                                   f"Maaş güncellenirken hata oluştu:\n{str(e)}")
            except Exception as e:
                QMessageBox.critical(self, "Beklenmeyen Hata", 
                                   f"Beklenmeyen bir hata oluştu:\n{str(e)}")

        update_salary_btn.clicked.connect(update_salary)

        # Layout'a ekle
        salary_layout = QHBoxLayout()
        salary_layout.addWidget(salary_edit)
        salary_layout.addWidget(update_salary_btn)
        vbox.addLayout(salary_layout)

        # Advances table
        year = QDate.currentDate().year()
        advances = self.employee.advances_for_month(month, year)
        self.advance_table = QTableWidget(len(advances), 3)
        self.advance_table.setHorizontalHeaderLabels(["Tarih", "Tutar", "Açıklama"])
        for row, (adv_id, date, amount, description) in enumerate(advances):
            date_item = QTableWidgetItem(date.toString("dd.MM.yyyy"))
            date_item.setData(Qt.UserRole, adv_id)  # Store advance ID for robust deletion
            self.advance_table.setItem(row, 0, date_item)
            self.advance_table.setItem(row, 1, QTableWidgetItem(f"{amount:.2f}"))
            self.advance_table.setItem(row, 2, QTableWidgetItem(description or ""))
        self.advance_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.advance_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.advance_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        vbox.addWidget(QLabel("Avanslar:"))
        vbox.addWidget(self.advance_table)

        # Buttons for advances
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Avans Ekle")
        delete_btn = QPushButton("Sil")
        update_btn = QPushButton("Güncelle")
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addWidget(update_btn)
        vbox.addLayout(btn_layout)

        # Hak ediş button (Final Settlement)
        hak_edis_btn = QPushButton("Hak Ediş")
        hak_edis_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        vbox.addWidget(hak_edis_btn)

        # Connect add_btn to add advance dialog and refresh tab
        def add_advance():
            dlg = AddAdvanceDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                date, amount, description = dlg.get_advance_data()
                if amount > 0:
                    # Validate that the advance date matches the current month being viewed
                    current_year = QDate.currentDate().year()
                    if date.month() != month or date.year() != current_year:
                        QMessageBox.warning(self, "Geçersiz Tarih", 
                                          f"Avans tarihi {month}. ay {current_year} ile eşleşmelidir!")
                        return
                    
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO advances (employee_id, date, amount, description) VALUES (?, ?, ?, ?)",
                            (self.employee.id, date.toString("yyyy-MM-dd"), amount, description)
                        )
                        conn.commit()
                        self.refresh_all_tabs()
                        QMessageBox.information(self, "Başarılı", "Avans başarıyla eklendi!")
                    except sqlite3.Error as e:
                        QMessageBox.critical(self, "Veritabanı Hatası", 
                                           f"Avans eklenirken hata oluştu:\n{str(e)}")
                    except Exception as e:
                        QMessageBox.critical(self, "Beklenmeyen Hata", 
                                           f"Beklenmeyen bir hata oluştu:\n{str(e)}")
                else:
                    QMessageBox.warning(self, "Geçersiz Değer", "Avans tutarı pozitif olmalıdır!")

        add_btn.clicked.connect(add_advance)

        # Implement "Sil" button functionality
        def delete_advance():
            # Always get the advances table from the current tab
            current_tab = self.tabs.currentWidget()
            advance_table = current_tab.findChild(QTableWidget)
            if advance_table is None:
                QMessageBox.warning(self, "Tablo Hatası", "Avans tablosu bulunamadı!")
                return

            selected_rows = advance_table.selectionModel().selectedRows()
            selected_items = advance_table.selectedItems()
            if not selected_rows and not selected_items:
                QMessageBox.warning(self, "Seçim Gerekli", "Lütfen silinecek avansı seçin!")
                return
            
            # Get selected row indices
            selected_indices = []
            if selected_rows:
                selected_indices = [r.row() for r in selected_rows]
            elif selected_items:
                # If no rows are selected but items are, get unique row indices
                selected_indices = list(set([item.row() for item in selected_items]))
            
            if not selected_indices:
                QMessageBox.warning(self, "Seçim Gerekli", "Lütfen silinecek avansı seçin!")
                return
            
            try:
                cursor = conn.cursor()
                deleted_count = 0
                debug_info = []
                for index in sorted(selected_indices, reverse=True):
                    adv_id_item = advance_table.item(index, 0)
                    if adv_id_item is not None:
                        adv_id = adv_id_item.data(Qt.UserRole)
                        debug_info.append(f"Row {index}: adv_id={adv_id}")
                        if adv_id is not None:
                            cursor.execute("""
                                DELETE FROM advances WHERE id = ?
                            """, (adv_id,))
                            deleted_count += 1
                        else:
                            debug_info.append(f"Row {index}: No adv_id found in UserRole!")
                    else:
                        debug_info.append(f"Row {index}: No item in column 0!")
                conn.commit()
                self.refresh_all_tabs()
                if deleted_count > 0:
                    QMessageBox.information(self, "Başarılı", f"{deleted_count} avans başarıyla silindi!\n{chr(10).join(debug_info)}")
                else:
                    QMessageBox.warning(self, "Silinemedi", f"Seçilen avans(lar) silinemedi.\n{chr(10).join(debug_info)}")
            except sqlite3.Error as e:
                QMessageBox.critical(self, "Veritabanı Hatası", 
                                   f"Avans silinirken hata oluştu:\n{str(e)}")
            except Exception as e:
                QMessageBox.critical(self, "Beklenmeyen Hata", 
                                   f"Beklenmeyen bir hata oluştu:\n{str(e)}")

        delete_btn.clicked.connect(delete_advance)

        # Implement "Güncelle" button functionality
        def update_advance():
            # Always get the advances table from the current tab
            current_tab = self.tabs.currentWidget()
            advance_table = current_tab.findChild(QTableWidget)
            if advance_table is None:
                QMessageBox.warning(self, "Tablo Hatası", "Avans tablosu bulunamadı!")
                return

            selected_rows = advance_table.selectionModel().selectedRows()
            selected_items = advance_table.selectedItems()
            
            # Get selected row indices
            selected_indices = []
            if selected_rows:
                selected_indices = [r.row() for r in selected_rows]
            elif selected_items:
                selected_indices = list(set([item.row() for item in selected_items]))
            
            if len(selected_indices) != 1:
                QMessageBox.warning(self, "Seçim Gerekli", "Lütfen güncellenecek avansı seçin!")
                return
            index = selected_indices[0]
            
            # Get the advance ID from the table
            adv_id_item = advance_table.item(index, 0)
            if adv_id_item is None:
                QMessageBox.warning(self, "Seçim Hatası", "Seçilen avans bulunamadı!")
                return
                
            adv_id = adv_id_item.data(Qt.UserRole)
            if adv_id is None:
                QMessageBox.warning(self, "Seçim Hatası", "Avans ID'si bulunamadı!")
                return

            # Get the current advance data from database
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT date, amount, description FROM advances WHERE id = ?
                """, (adv_id,))
                result = cursor.fetchone()
                if result is None:
                    QMessageBox.warning(self, "Veri Hatası", "Avans veritabanında bulunamadı!")
                    return
                    
                old_date_str, old_amount, old_description = result
                old_date = QDate.fromString(old_date_str, "yyyy-MM-dd")

                dlg = AddAdvanceDialog(self)
                dlg.setWindowTitle("Avans Güncelle")
                dlg.date_edit.setDate(old_date)
                dlg.amount_edit.setText(f"{old_amount:.2f}")
                dlg.description_edit.setText(old_description or "")

                if dlg.exec_() == QDialog.Accepted:
                    new_date, new_amount, new_description = dlg.get_advance_data()
                    if new_amount > 0:
                        # Validate that the advance date matches the current month being viewed
                        current_year = QDate.currentDate().year()
                        if new_date.month() != month or new_date.year() != current_year:
                            QMessageBox.warning(self, "Geçersiz Tarih", 
                                              f"Avans tarihi {month}. ay {current_year} ile eşleşmelidir!")
                            return
                        
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE advances SET date = ?, amount = ?, description = ?
                                WHERE id = ?
                            """, (
                                new_date.toString("yyyy-MM-dd"), new_amount, new_description, adv_id
                            ))
                            conn.commit()
                            self.refresh_all_tabs()
                            QMessageBox.information(self, "Başarılı", "Avans başarıyla güncellendi!")
                        except sqlite3.Error as e:
                            QMessageBox.critical(self, "Veritabanı Hatası", 
                                               f"Avans güncellenirken hata oluştu:\n{str(e)}")
                        except Exception as e:
                            QMessageBox.critical(self, "Beklenmeyen Hata", 
                                               f"Beklenmeyen bir hata oluştu:\n{str(e)}")
                    else:
                        QMessageBox.warning(self, "Geçersiz Değer", "Avans tutarı pozitif olmalıdır!")
            except sqlite3.Error as e:
                QMessageBox.critical(self, "Veritabanı Hatası", 
                                   f"Avans bilgisi alınırken hata oluştu:\n{str(e)}")
            except Exception as e:
                QMessageBox.critical(self, "Beklenmeyen Hata", 
                                   f"Beklenmeyen bir hata oluştu:\n{str(e)}")

        update_btn.clicked.connect(update_advance)

        # Hak ediş functionality
        def show_hak_edis():
            QMessageBox.information(self, "Hak Ediş", "Hak Ediş hesaplama özelliği yakında eklenecek!")

        hak_edis_btn.clicked.connect(show_hak_edis)

        tab.setLayout(vbox)
        return tab

    def refresh_tab(self, month):
        index = month - self.start_month
        if 0 <= index < self.tabs.count():
            self.tabs.removeTab(index)
            self.tabs.insertTab(index, self.create_month_tab(month), f"{month}. Ay")
            self.tabs.setCurrentIndex(index)
    
    def refresh_all_tabs(self):
        """Refresh all tabs to update kalan maaş calculations"""
        current_index = self.tabs.currentIndex()
        
        # Store the current tab index
        start_month = self.start_month
        current_year = QDate.currentDate().year()
        
        # Determine which months to show based on year
        if current_year == self.start_year:
            # First year: show from start month to December
            months_to_show = range(self.start_month, 13)
        else:
            # Subsequent years: show all 12 months
            months_to_show = range(1, 13)
        
        # Clear all tabs
        self.tabs.clear()
        
        # Recreate all tabs
        for month in months_to_show:
            self.tabs.addTab(self.create_month_tab(month), f"{month}. Ay")
        
        # Restore the current tab index
        if 0 <= current_index < self.tabs.count():
            self.tabs.setCurrentIndex(current_index)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.hotel_name = "Assos Kadırga Otel"  # You can change this to your hotel name
        self.setWindowTitle(f"{self.hotel_name} - Maaş Takip Sistemi")
        self.resize(600, 400)
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # Hotel Header
        header_label = QLabel(f"🏨 {self.hotel_name}")
        header_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
                padding: 10px;
                background-color: #ecf0f1;
                border-radius: 5px;
                margin: 5px;
            }
        """)
        header_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header_label)

        # Subtitle
        subtitle_label = QLabel("Çalışan Maaş Takip Sistemi")
        subtitle_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #7f8c8d;
                padding: 5px;
                margin-bottom: 10px;
            }
        """)
        subtitle_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(subtitle_label)

        # Employee Count Display
        self.employee_count_label = QLabel("Toplam Çalışan: 0")
        self.employee_count_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #27ae60;
                padding: 5px;
                background-color: #d5f4e6;
                border-radius: 3px;
                margin: 5px;
                font-weight: bold;
            }
        """)
        self.employee_count_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.employee_count_label)

        # Employee Table
        self.employee_table = QTableWidget(0, 2)
        self.employee_table.setHorizontalHeaderLabels(["Ad", "Soyad"])
        self.employee_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.employee_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.employee_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        main_layout.addWidget(self.employee_table)

        # Button Bar
        button_layout = QHBoxLayout()
        self.add_btn = QPushButton("Ekle")
        self.delete_btn = QPushButton("Sil")
        self.update_btn = QPushButton("Güncelle")
        button_layout.addWidget(self.add_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.update_btn)
        main_layout.addLayout(button_layout)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Data
        self.employees = []

        # System Tray Icon
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setVisible(True)

        # Signals
        self.add_btn.clicked.connect(self.add_employee)
        self.delete_btn.clicked.connect(self.delete_employee)
        self.update_btn.clicked.connect(self.update_employee)
        self.employee_table.cellDoubleClicked.connect(self.show_employee_detail)

        self.refresh_employee_table()

        # Timer to check salary due
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_salary_due)
        self.timer.start(3600000)  # check every hour instead of every minute
        
        # Track last notification date to prevent duplicates
        self.last_notification_date = None

    def add_employee(self):
        dialog = AddEmployeeDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            first, last, start_date, salary = dialog.get_employee_data()
            if first is None or last is None or start_date is None:
                # Validation error occurred, don't proceed
                return
            if first and last and salary > 0:
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO employees (first_name, last_name, start_date, salary) VALUES (?, ?, ?, ?)",
                        (first, last, start_date.toString("yyyy-MM-dd"), salary)
                    )
                    conn.commit()
                    self.refresh_employee_table()
                    QMessageBox.information(self, "Başarılı", "Çalışan başarıyla eklendi!")
                except sqlite3.Error as e:
                    QMessageBox.critical(self, "Veritabanı Hatası", 
                                       f"Çalışan eklenirken hata oluştu:\n{str(e)}")
                except Exception as e:
                    QMessageBox.critical(self, "Beklenmeyen Hata", 
                                       f"Beklenmeyen bir hata oluştu:\n{str(e)}")
            else:
                QMessageBox.warning(self, "Geçersiz Veri", 
                                  "Lütfen tüm alanları doldurun ve geçerli bir maaş girin!")

    def refresh_employee_table(self):
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, first_name, last_name, start_date, salary FROM employees ORDER BY first_name, last_name")
            rows = cursor.fetchall()
            self.employees = []
            self.employee_table.setRowCount(len(rows))
            for row_idx, (id_, first_name, last_name, start_date_str, salary) in enumerate(rows):
                start_date = QDate.fromString(start_date_str, "yyyy-MM-dd")
                emp = Employee(id_, first_name, last_name, start_date, salary)
                self.employees.append(emp)
                self.employee_table.setItem(row_idx, 0, QTableWidgetItem(first_name))
                self.employee_table.setItem(row_idx, 1, QTableWidgetItem(last_name))
            
            # Update employee count
            self.update_employee_count()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Veritabanı Hatası", 
                               f"Çalışan listesi yüklenirken hata oluştu:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Beklenmeyen Hata", 
                               f"Beklenmeyen bir hata oluştu:\n{str(e)}")

    def delete_employee(self):
        selected = self.employee_table.currentRow()
        if selected < 0 or selected >= len(self.employees):
            QMessageBox.warning(self, "Seçim Gerekli", "Lütfen silinecek çalışanı seçin!")
            return
        
        emp = self.employees[selected]
        
        # Ask for confirmation
        reply = QMessageBox.question(self, "Onay", 
                                   f"{emp.first_name} {emp.last_name} çalışanını silmek istediğinizden emin misiniz?\n\nBu işlem geri alınamaz!",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM employees WHERE id = ?", (emp.id,))
                conn.commit()
                self.refresh_employee_table()
                QMessageBox.information(self, "Başarılı", "Çalışan başarıyla silindi!")
            except sqlite3.Error as e:
                QMessageBox.critical(self, "Veritabanı Hatası", 
                                   f"Çalışan silinirken hata oluştu:\n{str(e)}")
            except Exception as e:
                QMessageBox.critical(self, "Beklenmeyen Hata", 
                                   f"Beklenmeyen bir hata oluştu:\n{str(e)}")

    def update_employee(self):
        selected = self.employee_table.currentRow()
        if selected < 0 or selected >= len(self.employees):
            QMessageBox.warning(self, "Seçim Gerekli", "Lütfen güncellenecek çalışanı seçin!")
            return
        emp = self.employees[selected]
        dialog = AddEmployeeDialog(self)
        dialog.first_name_edit.setText(emp.first_name)
        dialog.last_name_edit.setText(emp.last_name)
        dialog.start_date_edit.setDate(emp.start_date)
        dialog.salary_edit.setText(str(emp.salary))
        if dialog.exec_() == QDialog.Accepted:
            first, last, start_date, salary = dialog.get_employee_data()
            if first is None or last is None or start_date is None:
                # Validation error occurred, don't proceed
                return
            if first and last and salary > 0:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                                   UPDATE employees
                                   SET first_name = ?, last_name  = ?, start_date = ?, salary = ?
                                   WHERE id = ?
                    """, (first, last, start_date.toString("yyyy-MM-dd"), salary, emp.id))
                    conn.commit()
                    self.refresh_employee_table()
                    QMessageBox.information(self, "Başarılı", "Çalışan bilgileri başarıyla güncellendi!")
                except sqlite3.Error as e:
                    QMessageBox.critical(self, "Veritabanı Hatası", 
                                       f"Çalışan güncellenirken hata oluştu:\n{str(e)}")
                except Exception as e:
                    QMessageBox.critical(self, "Beklenmeyen Hata", 
                                       f"Beklenmeyen bir hata oluştu:\n{str(e)}")
            else:
                QMessageBox.warning(self, "Geçersiz Veri", 
                                  "Lütfen tüm alanları doldurun ve geçerli bir maaş girin!")

    def update_employee_count(self):
        """Update the employee count display"""
        count = len(self.employees)
        self.employee_count_label.setText(f"👥 Toplam Çalışan: {count}")
        
        # Change color based on count
        if count == 0:
            self.employee_count_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #e74c3c;
                    padding: 5px;
                    background-color: #fadbd8;
                    border-radius: 3px;
                    margin: 5px;
                    font-weight: bold;
                }
            """)
        elif count < 5:
            self.employee_count_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #f39c12;
                    padding: 5px;
                    background-color: #fdeaa7;
                    border-radius: 3px;
                    margin: 5px;
                    font-weight: bold;
                }
            """)
        else:
            self.employee_count_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: #27ae60;
                    padding: 5px;
                    background-color: #d5f4e6;
                    border-radius: 3px;
                    margin: 5px;
                    font-weight: bold;
                }
            """)

    def show_employee_detail(self, row, column):
        if 0 <= row < len(self.employees):
            emp = self.employees[row]
            dlg = EmployeeDetailDialog(emp, self)
            dlg.exec_()

    def check_salary_due(self):
        today = QDate.currentDate()
        
        # Prevent duplicate notifications on the same day
        if self.last_notification_date == today:
            return
            
        # Check for employees whose salary is due today
        due_employees = []
        for emp in self.employees:
            if emp.start_date.day() == today.day():
                due_employees.append(emp)
        
        if due_employees:
            # Create detailed notification message
            if len(due_employees) == 1:
                emp = due_employees[0]
                message = f"Bugün {emp.first_name} {emp.last_name} için maaş ödeme günü!"
            else:
                names = ", ".join(f"{emp.first_name} {emp.last_name}" for emp in due_employees)
                message = f"Bugün {len(due_employees)} çalışan için maaş ödeme günü:\n{names}"
            
            # Show system tray notification
            self.tray_icon.showMessage(
                f"💰 {self.hotel_name} - Maaş Ödeme Hatırlatıcısı",
                message,
                QSystemTrayIcon.Information,
                8000  # Show for 8 seconds
            )
            
            # Also show a dialog box for more visibility
            self.show_salary_due_dialog(due_employees)
            
            # Mark this date as notified
            self.last_notification_date = today
    
    def show_salary_due_dialog(self, due_employees):
        """Show a dialog box with salary due information"""
        msg = QMessageBox(self)
        msg.setWindowTitle(f"💰 {self.hotel_name} - Maaş Ödeme Hatırlatıcısı")
        msg.setIcon(QMessageBox.Information)
        
        if len(due_employees) == 1:
            emp = due_employees[0]
            msg.setText(f"Bugün {emp.first_name} {emp.last_name} için maaş ödeme günü!")
            msg.setInformativeText(f"Çalışan: {emp.first_name} {emp.last_name}\nMaaş: {emp.salary:.2f} TL")
        else:
            names = "\n".join(f"• {emp.first_name} {emp.last_name} ({emp.salary:.2f} TL)" for emp in due_employees)
            msg.setText(f"Bugün {len(due_employees)} çalışan için maaş ödeme günü!")
            msg.setInformativeText(f"Çalışanlar:\n{names}")
        
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setDefaultButton(QMessageBox.Ok)
        
        # Show the dialog but don't block the main window
        msg.show()


def main():
    try:
        initialize_database()
        app = QApplication(sys.argv)
        win = MainWindow()
        win.show()
        sys.exit(app.exec_())
    except Exception as e:
        QMessageBox.critical(None, "Kritik Hata", 
                           f"Uygulama başlatılırken kritik bir hata oluştu:\n{str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()