from PySide6.QtWidgets import(
    QPushButton,
    QDialog,
    QTextEdit,
    QVBoxLayout
)
from store import Storage

class DatatagDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Write Manual Datatag Description")
        self.layout = QVBoxLayout()
        self.okButton = QPushButton("Ok")
        self.datatagDescription = QTextEdit()
        self.okButton.clicked.connect(self.accept)
        self.okButton.setMaximumWidth(80)
        self.setModal(True)
        self.layout.addWidget(self.datatagDescription)
        self.layout.addWidget(self.okButton)
        self.setLayout(self.layout)
        self.resize(400,150)

class ManualDatatagButton(QPushButton):
    def __init__(self,msgFunction = None):
        super().__init__("Datatag")
        self.setToolTip("Write a manual datatag to the current active database.")
        self.clicked.connect(self.launchDatatagDialog)
        self.setMaximumWidth(70)
        if msgFunction is None:
            self.msgFunction = self.defaultMsg
        else:
            self.msgFunction = msgFunction

    def launchDatatagDialog(self):
        tagDialog = DatatagDialog()
        if tagDialog.exec() == QDialog.Accepted:
            description = tagDialog.datatagDescription.toPlainText()
            dtWriter = Storage(self.msgFunction)
            dtWriter.setActiveDatabase()
            dtWriter.writeDataTag("MAN",description)

    def defaultMsg(self,text,type):
        pass