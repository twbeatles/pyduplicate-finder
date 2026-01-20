from PySide6.QtGui import QColor, QPalette

class ModernTheme:
    """
    Centralized theme management for the application.
    Enhanced with modern design tokens and improved visual hierarchy.
    """
    
    LIGHT_PALETTE = {
        # Base colors
        "bg": "#f8f9fa",
        "fg": "#1a1a2e",
        "panel": "#ffffff",
        "border": "#e1e4e8",
        
        # Card & Container
        "card_bg": "#ffffff",
        "card_border": "#e8eaed",
        "card_shadow": "rgba(0, 0, 0, 0.06)",
        
        # Accent colors - Warm tones
        "primary": "#6366f1",  # Indigo (warmer than blue)
        "primary_hover": "#4f46e5",
        "primary_light": "#eef2ff",
        "success": "#10b981",
        "success_hover": "#059669",
        "success_light": "#d1fae5",
        "danger": "#ef4444",
        "danger_hover": "#dc2626",
        "danger_light": "#fee2e2",
        "warning": "#f59e0b",
        "warning_light": "#fef3c7",
        
        # Focus & Shadows
        "focus_ring": "rgba(0, 102, 255, 0.4)",
        "shadow_sm": "rgba(0, 0, 0, 0.05)",
        "shadow_md": "rgba(0, 0, 0, 0.1)",
        
        # Text
        "text_primary": "#1a1a2e",
        "text_secondary": "#6b7280",
        "text_tertiary": "#9ca3af",
        
        # Interactive
        "highlight": "#f0f7ff",
        "hover": "#f3f4f6",
        "active": "#e5e7eb",
        
        # Components
        "header_bg": "#f1f3f5",
        "input_bg": "#ffffff",
        "input_border": "#d1d5db",
        "input_focus": "#6366f1",
        
        # Tree/List specific - Warmer tones
        "group_bg": "#fef7ed",  # Warm cream
        "group_fg": "#78350f",  # Warm brown
        "group_border": "#fed7aa",
        "row_alt": "#fafbfc",
        
        # Preview
        "preview_bg": "#f5f6f7",
        "preview_border": "#e1e4e8",
        "preview_text": "#374151",
        
        # Scrollbar
        "scrollbar_bg": "#f1f3f5",
        "scrollbar_handle": "#c1c9d2",
        "scrollbar_hover": "#a8b2bd",
    }

    DARK_PALETTE = {
        # Base colors
        "bg": "#0d1117",
        "fg": "#e6edf3",
        "panel": "#161b22",
        "border": "#30363d",
        
        # Card & Container
        "card_bg": "#1c2128",
        "card_border": "#30363d",
        "card_shadow": "rgba(0, 0, 0, 0.4)",
        
        # Accent colors - Warm tones
        "primary": "#818cf8",  # Warmer indigo for dark mode
        "primary_hover": "#a5b4fc",
        "primary_light": "#312e81",
        "success": "#3fb950",
        "success_hover": "#56d364",
        "success_light": "#1f4d2e",
        "danger": "#f85149",
        "danger_hover": "#ff7b72",
        "danger_light": "#4d1f1f",
        "warning": "#d29922",
        "warning_light": "#4d3d1f",
        
        # Focus & Shadows
        "focus_ring": "rgba(88, 166, 255, 0.4)",
        "shadow_sm": "rgba(0, 0, 0, 0.2)",
        "shadow_md": "rgba(0, 0, 0, 0.3)",
        
        # Text
        "text_primary": "#e6edf3",
        "text_secondary": "#8b949e",
        "text_tertiary": "#6e7681",
        
        # Interactive
        "highlight": "#1f2937",
        "hover": "#21262d",
        "active": "#30363d",
        
        # Components
        "header_bg": "#161b22",
        "input_bg": "#0d1117",
        "input_border": "#30363d",
        "input_focus": "#818cf8",
        
        # Tree/List specific - Warmer tones
        "group_bg": "#292524",  # Warm stone
        "group_fg": "#fef3c7",  # Warm amber
        "group_border": "#44403c",
        "row_alt": "#161b22",
        
        # Preview
        "preview_bg": "#161b22",
        "preview_border": "#30363d",
        "preview_text": "#c9d1d9",
        
        # Scrollbar
        "scrollbar_bg": "#161b22",
        "scrollbar_handle": "#30363d",
        "scrollbar_hover": "#484f58",
    }

    @staticmethod
    def get_palette(mode="light"):
        return ModernTheme.DARK_PALETTE if mode == "dark" else ModernTheme.LIGHT_PALETTE

    @staticmethod
    def get_stylesheet(mode="light"):
        c = ModernTheme.get_palette(mode)
        
        return f"""
            /* ==================== GLOBAL RESET ==================== */
            QMainWindow, QDialog {{
                background-color: {c['bg']};
                color: {c['fg']};
            }}

            QWidget {{
                font-family: 'Segoe UI', 'Malgun Gothic', -apple-system, sans-serif;
                font-size: 14px;
                color: {c['text_primary']};
            }}

            QLabel {{
                color: {c['text_primary']};
                background: transparent;
            }}

            /* ==================== GROUPBOX (Card Style) ==================== */
            QGroupBox {{
                background-color: {c['card_bg']};
                border: 1px solid {c['card_border']};
                border-radius: 12px;
                margin-top: 20px;
                padding: 20px 16px 16px 16px;
                font-weight: 600;
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 16px;
                top: 8px;
                padding: 4px 12px;
                background-color: {c['primary']};
                color: #ffffff;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}

            /* ==================== BUTTONS ==================== */
            QPushButton {{
                background-color: {c['card_bg']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 10px 20px;
                color: {c['text_primary']};
                font-weight: 500;
                min-height: 20px;
            }}
            
            QPushButton:hover {{
                background-color: {c['hover']};
                border-color: {c['primary']};
            }}
            
            QPushButton:pressed {{
                background-color: {c['active']};
            }}
            
            QPushButton:disabled {{
                color: {c['text_tertiary']};
                background-color: {c['bg']};
                border-color: {c['border']};
            }}

            /* Primary Button - Enhanced with gradient */
            QPushButton#btn_primary {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c['success']}, stop:1 {c['success_hover']});
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-weight: 600;
                font-size: 14px;
                padding: 12px 24px;
            }}
            QPushButton#btn_primary:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c['success_hover']}, stop:1 {c['success']});
            }}
            QPushButton#btn_primary:pressed {{
                background: {c['success_hover']};
                padding-top: 13px;
                padding-bottom: 11px;
            }}
            QPushButton#btn_primary:disabled {{
                background: {c['border']};
                color: {c['text_tertiary']};
            }}

            /* Danger Button - Enhanced with gradient */
            QPushButton#btn_danger {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c['danger']}, stop:1 {c['danger_hover']});
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-weight: 600;
                font-size: 14px;
                padding: 12px 24px;
            }}
            QPushButton#btn_danger:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c['danger_hover']}, stop:1 {c['danger']});
            }}
            QPushButton#btn_danger:pressed {{
                background: {c['danger_hover']};
                padding-top: 13px;
                padding-bottom: 11px;
            }}

            /* Secondary Button - Enhanced with outline style */
            QPushButton#btn_secondary {{
                background-color: transparent;
                border: 2px solid {c['primary']};
                border-radius: 10px;
                color: {c['primary']};
                font-weight: 600;
                padding: 10px 22px;
            }}
            QPushButton#btn_secondary:hover {{
                background-color: {c['primary_light']};
                border-color: {c['primary_hover']};
            }}
            QPushButton#btn_secondary:pressed {{
                background-color: {c['primary']};
                color: #ffffff;
            }}

            /* Icon Button - Compact style for toolbar-like buttons */
            QPushButton#btn_icon {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 8px 12px;
                min-width: 32px;
            }}
            QPushButton#btn_icon:hover {{
                background-color: {c['hover']};
                border-color: {c['border']};
            }}

            /* ==================== INPUT FIELDS ==================== */
            QLineEdit, QSpinBox {{
                background-color: {c['input_bg']};
                border: 1px solid {c['input_border']};
                border-radius: 8px;
                padding: 10px 12px;
                color: {c['text_primary']};
                selection-background-color: {c['primary']};
                selection-color: #ffffff;
            }}
            
            QLineEdit:focus, QSpinBox:focus {{
                border: 2px solid {c['input_focus']};
                padding: 9px 11px;
            }}
            
            QLineEdit:disabled, QSpinBox:disabled {{
                background-color: {c['bg']};
                color: {c['text_tertiary']};
            }}
            
            QLineEdit::placeholder {{
                color: {c['text_tertiary']};
            }}

            /* ==================== CHECKBOX ==================== */
            QCheckBox {{
                spacing: 10px;
                color: {c['text_primary']};
                padding: 4px 0;
            }}
            
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {c['input_border']};
                border-radius: 6px;
                background-color: {c['input_bg']};
            }}
            
            QCheckBox::indicator:hover {{
                border-color: {c['primary']};
            }}
            
            QCheckBox::indicator:checked {{
                background-color: {c['primary']};
                border-color: {c['primary']};
            }}

            /* ==================== LIST WIDGET ==================== */
            QListWidget {{
                background-color: {c['input_bg']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: 6px;
                margin: 2px 4px;
                color: {c['text_primary']};
            }}
            
            QListWidget::item:selected {{
                background-color: {c['primary']};
                color: #ffffff;
            }}
            
            QListWidget::item:hover:!selected {{
                background-color: {c['hover']};
            }}

            /* ==================== TREE WIDGET ==================== */
            QTreeWidget {{
                background-color: {c['input_bg']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 4px;
                outline: none;
                alternate-background-color: {c['row_alt']};
            }}
            
            QTreeWidget::item {{
                padding: 8px 6px;
                border-radius: 4px;
                min-height: 32px;
            }}
            
            QTreeWidget::item:selected {{
                background-color: {c['primary']};
                color: #ffffff;
            }}
            
            QTreeWidget::item:hover:!selected {{
                background-color: {c['hover']};
            }}
            
            QTreeWidget::branch {{
                background: transparent;
            }}

            /* Tree Header */
            QHeaderView::section {{
                background-color: {c['header_bg']};
                color: {c['text_secondary']};
                padding: 12px 8px;
                border: none;
                border-right: 1px solid {c['border']};
                border-bottom: 2px solid {c['border']};
                font-weight: 600;
                font-size: 13px;
            }}
            
            QHeaderView::section:first {{
                border-top-left-radius: 8px;
            }}
            
            QHeaderView::section:last {{
                border-right: none;
                border-top-right-radius: 8px;
            }}

            /* ==================== SCROLLBARS ==================== */
            QScrollBar:vertical {{
                background: {c['scrollbar_bg']};
                width: 14px;
                margin: 4px 2px;
                border-radius: 7px;
            }}
            
            QScrollBar::handle:vertical {{
                background: {c['scrollbar_handle']};
                min-height: 30px;
                border-radius: 5px;
                margin: 2px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background: {c['scrollbar_hover']};
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            QScrollBar:horizontal {{
                background: {c['scrollbar_bg']};
                height: 14px;
                margin: 2px 4px;
                border-radius: 7px;
            }}
            
            QScrollBar::handle:horizontal {{
                background: {c['scrollbar_handle']};
                min-width: 30px;
                border-radius: 5px;
                margin: 2px;
            }}
            
            QScrollBar::handle:horizontal:hover {{
                background: {c['scrollbar_hover']};
            }}

            /* ==================== SPLITTER ==================== */
            QSplitter::handle {{
                background-color: {c['bg']};
            }}
            
            QSplitter::handle:vertical {{
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 transparent, stop:0.4 {c['border']}, 
                    stop:0.6 {c['border']}, stop:1 transparent);
                margin: 4px 40px;
            }}
            
            QSplitter::handle:horizontal {{
                width: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 transparent, stop:0.4 {c['border']}, 
                    stop:0.6 {c['border']}, stop:1 transparent);
                margin: 40px 4px;
            }}
            
            QSplitter::handle:hover {{
                background: {c['primary']};
                border-radius: 4px;
            }}

            /* ==================== TOOLBAR ==================== */
            QToolBar {{
                background: {c['panel']};
                border: none;
                border-bottom: 1px solid {c['border']};
                spacing: 8px;
                padding: 8px 12px;
            }}
            
            QToolBar::separator {{
                width: 1px;
                background: {c['border']};
                margin: 4px 8px;
            }}
            
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                color: {c['text_primary']};
                font-weight: 500;
            }}
            
            QToolButton:hover {{
                background-color: {c['hover']};
            }}
            
            QToolButton:pressed {{
                background-color: {c['active']};
            }}
            
            QToolButton:checked {{
                background-color: {c['primary_light']};
                color: {c['primary']};
            }}

            /* ==================== PROGRESS BAR ==================== */
            QProgressBar {{
                border: none;
                border-radius: 6px;
                background-color: {c['bg']};
                text-align: center;
                color: {c['text_secondary']};
                font-size: 12px;
            }}
            
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['primary']}, stop:1 {c['success']});
                border-radius: 6px;
            }}

            /* ==================== MENU ==================== */
            QMenu {{
                background-color: {c['card_bg']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 6px;
            }}
            
            QMenu::item {{
                padding: 10px 32px 10px 16px;
                border-radius: 6px;
                color: {c['text_primary']};
            }}
            
            QMenu::item:selected {{
                background-color: {c['hover']};
            }}
            
            QMenu::separator {{
                height: 1px;
                background: {c['border']};
                margin: 6px 8px;
            }}

            /* ==================== MESSAGE BOX / DIALOG ==================== */
            QMessageBox, QProgressDialog {{
                background-color: {c['card_bg']};
            }}
            
            QMessageBox QLabel, QProgressDialog QLabel {{
                color: {c['text_primary']};
                font-size: 14px;
            }}
            
            QMessageBox QPushButton, QProgressDialog QPushButton {{
                min-width: 80px;
            }}

            /* ==================== SCROLL AREA ==================== */
            QScrollArea {{
                background-color: {c['preview_bg']};
                border: 1px solid {c['preview_border']};
                border-radius: 8px;
            }}
            
            QScrollArea > QWidget > QWidget {{
                background-color: {c['preview_bg']};
            }}

            /* ==================== TEXT EDIT (Preview) ==================== */
            QTextEdit {{
                background-color: {c['input_bg']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 12px;
                color: {c['text_primary']};
                selection-background-color: {c['primary']};
            }}

            /* ==================== TOOLTIP ==================== */
            QToolTip {{
                background-color: {c['card_bg']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}

            /* ==================== STATUS LABEL ==================== */
            QLabel#status_label {{
                color: {c['text_secondary']};
                font-size: 13px;
                padding: 4px 8px;
            }}

            /* ==================== SIDEBAR ==================== */
            QWidget#sidebar {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {c['primary']}, stop:1 {c['primary_hover']});
                border: none;
                border-right: 1px solid rgba(255, 255, 255, 0.1);
            }}
            
            QWidget#sidebar QLabel#sidebar_logo {{
                color: rgba(255, 255, 255, 0.95);
                background: transparent;
            }}
            
            QWidget#sidebar QPushButton {{
                background: transparent;
                border: none;
                border-radius: 12px;
                padding: 12px;
                margin: 2px 6px;
                color: rgba(255, 255, 255, 0.75);
            }}
            
            QWidget#sidebar QPushButton:hover {{
                background: rgba(255, 255, 255, 0.15);
                color: #ffffff;
            }}
            
            QWidget#sidebar QPushButton:checked {{
                background: rgba(255, 255, 255, 0.25);
                color: #ffffff;
            }}

            /* ==================== CARD COMPONENTS ==================== */
            QWidget#folder_card {{
                background-color: {c['card_bg']};
                border: 1px solid {c['card_border']};
                border-radius: 16px;
            }}
            
            QWidget#filter_card {{
                background-color: {c['card_bg']};
                border: 1px solid {c['card_border']};
                border-radius: 16px;
            }}
            
            QWidget#result_card {{
                background-color: {c['card_bg']};
                border: 1px solid {c['card_border']};
                border-radius: 16px;
            }}
            
            QWidget#preview_card {{
                background-color: {c['preview_bg']};
                border: 1px solid {c['preview_border']};
                border-radius: 16px;
            }}

            /* ==================== FLOATING ACTION BAR ==================== */
            QWidget#action_bar {{
                background-color: {c['panel']};
                border-top: 1px solid {c['border']};
                padding: 0px;
            }}
            
            QWidget#action_bar QPushButton {{
                min-height: 40px;
                padding: 10px 24px;
                font-weight: 600;
                border-radius: 10px;
            }}

            /* ==================== COMPACT HEADER ==================== */
            QLabel#section_header {{
                font-weight: 600;
                font-size: 13px;
                color: {c['text_secondary']};
                padding: 8px 0px;
                background: transparent;
            }}
            
            QLabel#card_title {{
                font-weight: 700;
                font-size: 15px;
                color: {c['text_primary']};
                background: transparent;
            }}

            /* ==================== ENHANCED TREE CHECKBOX ==================== */
            QTreeWidget::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {c['input_border']};
                border-radius: 5px;
                background: {c['input_bg']};
            }}
            
            QTreeWidget::indicator:hover {{
                border-color: {c['primary']};
            }}
            
            QTreeWidget::indicator:checked {{
                background-color: {c['danger']};
                border-color: {c['danger']};
            }}

            /* ==================== STACKED WIDGET PAGES ==================== */
            QStackedWidget {{
                background: transparent;
            }}
        """

