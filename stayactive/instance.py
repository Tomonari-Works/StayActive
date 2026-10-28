"""QLockFile の排他と、ローカルソケットによる既存ウィンドウの復帰。"""

import hashlib
from pathlib import Path

from PyQt6.QtCore import QObject, QLockFile, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activated = pyqtSignal()

    def __init__(self, directory: Path):
        super().__init__()
        self.lock = QLockFile(str(directory / "instance.lock"))
        self.lock.setStaleLockTime(0)
        digest = hashlib.sha256(str(directory.resolve()).casefold().encode()).hexdigest()[:24]
        self.name = "stayactive-" + digest
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)

    def acquire(self):
        if not self.lock.tryLock(0):
            if self.lock.error() != QLockFile.LockError.LockFailedError:
                raise OSError("アプリの排他ロックを作成できません。 / Could not create the application lock.")
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise OSError("既存画面への接続を準備できません。 / Could not open the local activation socket.")
        return True

    def activate_existing(self):
        for _ in range(3):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(250):
                socket.disconnectFromServer()
                return True
        return False

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.disconnectFromServer()
            socket.deleteLater()
            self.activated.emit()

    def close(self):
        self.server.close()
        self.lock.unlock()
