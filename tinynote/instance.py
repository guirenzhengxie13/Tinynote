"""A local socket for showing or cleanly closing an existing instance."""
import hashlib
from PySide6.QtCore import QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def instance_name(root):
    return "tinynote-" + hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()[:24]


def send_command(root, command):
    socket = QLocalSocket()
    socket.connectToServer(instance_name(root))
    if not socket.waitForConnected(500):
        return False
    socket.write((command + "\n").encode())
    socket.waitForBytesWritten(500)
    if not socket.bytesAvailable() and not socket.waitForReadyRead(2000):
        return False
    return bytes(socket.readAll()).strip() == b"ok"


class InstanceServer(QObject):
    def __init__(self, root, window):
        super().__init__(window)
        self.window = window
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.accept)
        name = instance_name(root)
        QLocalServer.removeServer(name)
        if not self.server.listen(name):
            raise OSError("无法创建本地启动通道")

    def accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self.read(s))
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                self.read(socket)

    def read(self, socket):
        if not socket.canReadLine():
            return
        command = bytes(socket.readLine()).strip()
        ok = False
        if command == b"show":
            self.window.show_note()
            ok = True
        elif command == b"quit":
            ok = self.window.flush()
            if ok:
                QTimer.singleShot(100, self.window.quit)
        socket.write(b"ok\n" if ok else b"error\n")
        socket.flush()
        socket.disconnectFromServer()
