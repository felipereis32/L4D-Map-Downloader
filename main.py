import json
import os
import subprocess
import sys
from pathlib import Path
from threading import Event
import threading
import time
from PySide6.QtCore import QObject, QThread, Signal, Qt, QUrl, QMetaObject, Q_ARG, Slot
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from game_detector import SteamGameDetector
from gamemaps import buscar_mapas, verificar_conexao, obter_link_download
from downloader import GerenciadorDownloads, formatar_tamanho
from idiomas import definir_idioma, _, IDIOMAS_DISPONIVEIS


APP_ID = "500"
if getattr(sys, "frozen", False):
    PASTA_APLICATIVO = Path(sys.executable).resolve().parent
else:
    PASTA_APLICATIVO = Path(__file__).resolve().parent

ARQUIVO_CONFIG = PASTA_APLICATIVO / "config.json"


def caminho_recurso(nome):
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent

    return base / nome


CONFIG_PADRAO = {
    "idioma": "pt_BR",
    "tema": "escuro",
    "pasta_jogo": "",
    "downloads_simultaneos": 3,
}

IDIOMAS = list(IDIOMAS_DISPONIVEIS.items())


def criar_caixa_mensagem(parent, titulo, texto, icone=QMessageBox.Icon.Information, botoes=None):
    msg = QMessageBox(parent)
    msg.setWindowTitle(titulo)
    msg.setText(texto)
    msg.setIcon(icone)
    
    botoes_dict = {}
    if botoes is None:
        botoes = [(_("comum.ok"), QMessageBox.ButtonRole.AcceptRole)]
        
    for texto_btn, papel in botoes:
        btn = msg.addButton(texto_btn, papel)
        botoes_dict[texto_btn] = btn
        
    msg.exec()
    return msg.clickedButton()


class JanelaEscolhaIdioma(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.idioma_selecionado = "pt_BR"
        self.setWindowTitle(_("app.nome"))
        self.setFixedSize(380, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        titulo = QLabel(_("idioma.rotulo_selecao"))
        titulo.setStyleSheet("font-size: 11pt; font-weight: bold;")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)

        self.combo = QComboBox()
        for codigo, nome in IDIOMAS:
            self.combo.addItem(nome, codigo)
        
        self.combo.setCurrentIndex(0)
        layout.addWidget(self.combo)

        layout.addStretch()

        btn_confirmar = QPushButton(_("comum.ok"))
        btn_confirmar.setObjectName("Primary")
        btn_confirmar.clicked.connect(self.confirmar)
        layout.addWidget(btn_confirmar)

    def confirmar(self):
        self.idioma_selecionado = self.combo.currentData()
        self.accept()


def carregar_configuracoes():
    configuracoes = CONFIG_PADRAO.copy()

    try:
        if ARQUIVO_CONFIG.exists():
            with ARQUIVO_CONFIG.open("r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)

            if isinstance(dados, dict):
                for chave in CONFIG_PADRAO:
                    if chave in dados:
                        configuracoes[chave] = dados[chave]

    except (OSError, json.JSONDecodeError):
        pass

    codigos_validos = {codigo for codigo, _ in IDIOMAS}

    if configuracoes["idioma"] not in codigos_validos:
        configuracoes["idioma"] = "pt_BR"

    if configuracoes["tema"] not in {"escuro", "claro"}:
        configuracoes["tema"] = "escuro"

    if not isinstance(configuracoes["pasta_jogo"], str):
        configuracoes["pasta_jogo"] = ""

    try:
        configuracoes["downloads_simultaneos"] = max(
            1,
            min(int(configuracoes["downloads_simultaneos"]), 10),
        )
    except (TypeError, ValueError):
        configuracoes["downloads_simultaneos"] = 3

    return configuracoes


def salvar_configuracoes(configuracoes):
    temporario = ARQUIVO_CONFIG.with_suffix(".tmp")

    try:
        with temporario.open("w", encoding="utf-8") as arquivo:
            json.dump(
                configuracoes,
                arquivo,
                ensure_ascii=False,
                indent=4,
            )

        temporario.replace(ARQUIVO_CONFIG)
        return True

    except OSError:
        try:
            temporario.unlink(missing_ok=True)
        except OSError:
            pass

        return False


def aplicar_tema(aplicativo, tema):
    if tema == "claro":
        aplicativo.setStyleSheet("""
            QWidget {
                background-color: #f4f6fa;
                color: #172033;
                font-size: 10pt;
            }
            QFrame#Sidebar {
                background-color: #e8edf5;
                border: none;
            }
            QFrame#Panel, QFrame#MapCard {
                background-color: #ffffff;
                border: 1px solid #d8deea;
                border-radius: 12px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 7px;
                padding: 8px;
            }
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8fafc, stop:1 #e2e8f0);
                border: 1px solid #cbd5e1;
                border-bottom: 2px solid #94a3b8;
                border-radius: 8px;
                padding: 9px 12px;
                font-weight: bold;
                color: #172033;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #edf2f7);
                border: 1px solid #94a3b8;
                border-bottom: 2px solid #64748b;
            }
            QPushButton:pressed {
                background-color: #cbd5e1;
                border-bottom: 1px solid #cbd5e1;
                padding-top: 10px;
            }
            QPushButton#Primary,
            QPushButton#NavigationActive {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #1d4ed8);
                color: white;
                border: 1px solid #1d4ed8;
                border-bottom: 2px solid #1e3a8a;
                font-weight: bold;
            }
            QPushButton#Primary:hover,
            QPushButton#NavigationActive:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #60a5fa, stop:1 #2563eb);
                border-bottom: 2px solid #1d4ed8;
            }
            QPushButton#Primary:pressed,
            QPushButton#NavigationActive:pressed {
                background-color: #1d4ed8;
                border-bottom: 1px solid #1d4ed8;
                padding-top: 10px;
            }
            QPushButton#Success {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #22c55e, stop:1 #15803d);
                color: white;
                border: 1px solid #15803d;
                border-bottom: 2px solid #14532d;
                font-weight: bold;
            }
            QPushButton#Success:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4ade80, stop:1 #16a34a);
                border-bottom: 2px solid #15803d;
            }
            QPushButton#Success:pressed {
                background-color: #15803d;
                border-bottom: 1px solid #15803d;
                padding-top: 10px;
            }
            QProgressBar {
                background-color: #e2e8f2;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                text-align: center;
                color: #172033;
                font-weight: bold;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #16a34a;
                border-radius: 5px;
            }
        """)
    else:
        aplicativo.setStyleSheet("""
            QWidget {
                background-color: #111827;
                color: #e5e7eb;
                font-size: 10pt;
            }
            QFrame#Sidebar {
                background-color: #0b1220;
                border: none;
            }
            QFrame#Panel, QFrame#MapCard {
                background-color: #1b2638;
                border: 1px solid #2b3a50;
                border-radius: 12px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #202d42;
                border: 1px solid #34445c;
                border-radius: 7px;
                padding: 8px;
            }
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #253650, stop:1 #1b2638);
                border: 1px solid #34445c;
                border-bottom: 3px solid #0f172a;
                border-radius: 8px;
                padding: 9px 12px;
                font-weight: bold;
                color: #e5e7eb;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2f4363, stop:1 #202d42);
                border: 1px solid #475569;
                border-bottom: 3px solid #1e293b;
            }
            QPushButton:pressed {
                background-color: #151c28;
                border-bottom: 1px solid #1b2638;
                padding-top: 10px;
            }
            QPushButton#Primary,
            QPushButton#NavigationActive {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #1d4ed8);
                color: white;
                border: 1px solid #1d4ed8;
                border-bottom: 3px solid #1e3a8a;
                font-weight: bold;
            }
            QPushButton#Primary:hover,
            QPushButton#NavigationActive:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #60a5fa, stop:1 #2563eb);
                border-bottom: 3px solid #1d4ed8;
            }
            QPushButton#Primary:pressed,
            QPushButton#NavigationActive:pressed {
                background-color: #1d4ed8;
                border-bottom: 1px solid #1d4ed8;
                padding-top: 10px;
            }
            QPushButton#Success {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #22c55e, stop:1 #15803d);
                color: white;
                border: 1px solid #15803d;
                border-bottom: 3px solid #14532d;
                font-weight: bold;
            }
            QPushButton#Success:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4ade80, stop:1 #16a34a);
                border-bottom: 3px solid #15803d;
            }
            QPushButton#Success:pressed {
                background-color: #151c28;
                border-bottom: 1px solid #1b2638;
                padding-top: 10px;
            }
            QProgressBar {
                background-color: #202d42;
                border: 1px solid #34445c;
                border-radius: 6px;
                text-align: center;
                color: #e5e7eb;
                font-weight: bold;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #16a34a;
                border-radius: 5px;
            }
        """)


class DialogoPopInSucesso(QDialog):
    def __init__(self, parent=None, mensagem=""):
        super().__init__(parent)
        self.setWindowTitle(_("app.nome"))
        self.setFixedSize(460, 170)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        
        lbl_msg = QLabel(mensagem)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("font-size: 10pt; line-height: 1.4;")
        layout.addWidget(lbl_msg)
        
        layout.addStretch()
        
        btn_ok = QPushButton(_("comum.ok"))
        btn_ok.setObjectName("Primary")
        btn_ok.setFixedWidth(120)
        btn_ok.clicked.connect(self.accept)
        
        layout.addWidget(btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)


class LogoL4D(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(188, 110)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        caminho = caminho_recurso("l4d1logo.jpg")
        if caminho.exists():
            pixmap = QPixmap(str(caminho)).scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(pixmap)
        else:
            self.setText(_("app.logo_ausente"))
            self.setStyleSheet("color: #f87171; font-size: 8pt; border: 1px dashed #f87171;")


class BannerL4D(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(210)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(True)
        
        caminho = caminho_recurso("L4dBanner.png")
        if caminho.exists():
            pixmap = QPixmap(str(caminho))
            pixmap_ajustado = pixmap.scaled(
                900, 210,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(pixmap_ajustado)
            self.setStyleSheet("border-radius: 10px; background-color: #0b1220;")
        else:
            self.setText(_("app.banner_ausente"))
            self.setStyleSheet("color: #94a3b8; font-size: 10pt; border: 1px dashed #34445c; border-radius: 10px;")


class TrabalhadorConexao(QObject):
    terminou = Signal(bool, str)

    def executar(self):
        try:
            ok = bool(verificar_conexao())
        except Exception as erro:
            ok = False
            try:
                mensagem = _("conexao.erro", erro=str(erro))
            except Exception:
                mensagem = _("conexao.erro_simples", erro=str(erro))
        else:
            chave = "conexao.sucesso" if ok else "conexao.falha"
            try:
                mensagem = _(chave)
            except Exception:
                mensagem = _("conexao.estabelecida") if ok else _("conexao.falha")

        self.terminou.emit(ok, mensagem)


class TrabalhadorBusca(QObject):
    terminou = Signal(int, str, list, bool)
    progresso = Signal(int, str, int, int)
    falha = Signal(int, str, str)

    def __init__(self, id_busca, termo, cancelar):
        super().__init__()
        self.id_busca = id_busca
        self.termo = termo
        self.cancelar = cancelar

    def executar(self):
        try:
            resultados = buscar_mapas(
                self.termo,
                cancelar=self.cancelar,
                progresso=lambda pagina, total: (
                    self.progresso.emit(
                        self.id_busca,
                        self.termo,
                        pagina,
                        total,
                    )
                ),
            )

            self.terminou.emit(
                self.id_busca,
                self.termo,
                resultados or [],
                self.cancelar.is_set(),
            )

        except Exception as erro:
            self.falha.emit(
                self.id_busca,
                self.termo,
                str(erro),
            )

            self.terminou.emit(
                self.id_busca,
                self.termo,
                [],
                self.cancelar.is_set(),
            )


class CartaoCampanha(QFrame):
    alteracao_selecao = Signal(dict, bool)

    def __init__(self, campanha, selecionada=False, parent=None):
        super().__init__(parent)

        self.campanha = campanha

        self.setObjectName("MapCard")
        self.setMinimumHeight(70)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        coluna = QVBoxLayout()
        coluna.setSpacing(6)

        nome = QLabel(campanha.get("nome") or _("busca.campanha_sem_nome"))
        nome.setWordWrap(True)
        nome.setStyleSheet("font-size: 12pt; font-weight: bold;")
        coluna.addWidget(nome)

        self.link = QPushButton(_("busca.ver_no_gamemaps"))
        self.link.setFixedWidth(160)
        self.link.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self.campanha["url"]))
        )
        coluna.addWidget(self.link, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(coluna, 1)

        self.checkbox = QCheckBox(_("busca.selecionar"))
        self.checkbox.setChecked(selecionada)
        self.checkbox.stateChanged.connect(self._notificar_selecao)

        layout.addWidget(self.checkbox, alignment=Qt.AlignmentFlag.AlignCenter)

    def _notificar_selecao(self, estado):
        self.alteracao_selecao.emit(
            self.campanha,
            estado == Qt.CheckState.Checked.value,
        )


class JanelaPrincipal(QMainWindow):
    def __init__(self, configuracoes):
        super().__init__()

        self.id_busca_atual = 0
        self.threads_busca_ativas = []
        self._ultimo_update_progresso = 0.0
        self._progresso_downloads_cache = {}

        self.configuracoes = configuracoes
        self.detector = SteamGameDetector()
        self.pasta_jogo = configuracoes.get("pasta_jogo", "")

        self.conexao_ok = False
        self.thread_conexao = None
        self.trabalhador_conexao = None

        self.thread_busca = None
        self.trabalhador_busca = None
        self.cancelamento_busca = None

        self.gerenciador_downloads = GerenciadorDownloads(
            downloads_simultaneos=configuracoes.get("downloads_simultaneos", 3),
            on_progresso=self.ao_atualizar_progresso_download,
            on_mensagem=self.ao_atualizar_mensagem_download,
            on_concluido=self.ao_concluir_download,
        )

        self.resultados_atuais = []
        self.campanhas_selecionadas = {}
        self.cartoes = []
        self.checkboxes_addons = {}

        self.setWindowTitle(_("app.nome"))
        self.resize(1180, 760)
        self.setMinimumSize(850, 560)

        central = QWidget()
        self.setCentralWidget(central)

        principal = QHBoxLayout(central)
        principal.setContentsMargins(0, 0, 0, 0)
        principal.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(220)

        self.menu_layout = QVBoxLayout(self.sidebar)
        self.menu_layout.setContentsMargins(16, 20, 16, 18)
        self.menu_layout.setSpacing(10)

        self.logo_widget = LogoL4D()
        self.menu_layout.addWidget(self.logo_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        self.menu_layout.addSpacing(10)

        self.pilha = QStackedWidget()
        self.paginas = {}
        self.botoes_navegacao = {}

        self.itens_menu = [
            ("inicio", "menu.inicio"),
            ("buscar", "menu.buscar"),
            ("selecionadas", "menu.selecionadas"),
            ("addons", "menu.addons"),
            ("config", "menu.configuracoes"),
        ]

        for chave, chave_trad in self.itens_menu:
            botao = QPushButton(_(chave_trad))
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.clicked.connect(
                lambda _checked=False, k=chave: self.mostrar_pagina(k)
            )
            self.menu_layout.addWidget(botao)
            self.botoes_navegacao[chave] = botao

        self.menu_layout.addStretch()

        self.status_sidebar = QLabel(_("conexao.verificando"))
        self.status_sidebar.setWordWrap(True)
        self.status_sidebar.setStyleSheet("color: #fbbf24;")
        self.menu_layout.addWidget(self.status_sidebar)

        principal.addWidget(self.sidebar)
        principal.addWidget(self.pilha, 1)

        self.criar_pagina_inicio()
        self.criar_pagina_buscar()
        self.criar_pagina_selecionadas()
        self.criar_pagina_addons()
        self.criar_pagina_configuracoes()

        aplicar_tema(QApplication.instance(), self.configuracoes["tema"])
        self.mostrar_pagina("inicio")

        self.iniciar_verificacao_conexao()
        self.detectar_jogo()

    def retraduzir_interface(self):
        self.setWindowTitle(_("app.nome"))

        for chave, chave_trad in self.itens_menu:
            if chave in self.botoes_navegacao:
                self.botoes_navegacao[chave].setText(_(chave_trad))

        self.lbl_inicio_titulo.setText(_("inicio.titulo"))
        self.lbl_inicio_desc.setText(_("inicio.descricao"))
        self.lbl_inicio_status.setText(_("inicio.status_sistema"))
        self.btn_inicio_selecionar.setText(_("inicio.selecionar_pasta"))
        self.lbl_inicio_acesso.setText(_("inicio.acesso_rapido"))
        self.btn_inicio_buscar.setText(_("inicio.buscar_campanhas"))
        self.btn_inicio_selecionadas.setText(_("inicio.ver_selecionadas"))

        self.lbl_buscar_titulo.setText(_("busca.titulo"))
        self.lbl_buscar_desc.setText(_("busca.descricao"))
        self.campo_busca.setPlaceholderText(_("busca.placeholder"))
        self.botao_buscar.setText(_("busca.pesquisar"))
        self.botao_cancelar_busca.setText(_("busca.cancelar"))
        self.status_busca.setText(_("busca.instrucoes"))
        self.lbl_buscar_selecao.setText(_("busca.sua_selecao"))
        self.botao_baixar_selecionados.setText(_("selecionadas.baixar_instalar"))
        self.botao_remover_selecionados.setText(_("selecionadas.limpar"))
        self.progresso_download.setText(_("downloads.nenhum_iniciado"))
        self.botao_cancelar_download.setText(_("downloads.cancelar_ativos"))
        self.btn_ver_selecionadas.setText(_("busca.gerenciar_selecao"))

        self.lbl_selec_titulo.setText(_("selecionadas.titulo"))
        self.lbl_selec_desc.setText(_("selecionadas.descricao"))
        self.btn_baixar_todos.setText(_("selecionadas.baixar_instalar"))
        self.btn_limpar_selecao.setText(_("selecionadas.limpar"))
        self.lbl_selec_aviso.setText(_("selecionadas.aviso"))

        self.lbl_addons_titulo.setText(_("addons.titulo"))
        self.lbl_addons_desc.setText(_("addons.descricao"))
        self.btn_addons_abrir.setText(_("addons.abrir_pasta"))
        self.btn_addons_atualizar.setText(_("addons.atualizar_lista"))
        self.lbl_addons_nota.setText(_("addons.aviso"))
        self.botao_selecionar_todos_addons.setText(_("addons.selecionar_todos"))
        self.botao_apagar_addons.setText(_("addons.remover_selecionados"))

        self.lbl_config_titulo.setText(_("config.titulo"))
        self.lbl_config_desc.setText(_("config.descricao"))
        self.lbl_config_idioma.setText(_("config.idioma"))
        self.lbl_config_tema.setText(_("config.tema"))
        self.lbl_config_downloads.setText(_("config.downloads_simultaneos"))
        self.lbl_config_pasta.setText(_("config.pasta_jogo"))
        self.btn_config_procurar.setText(_("comum.procurar"))
        self.btn_config_salvar.setText(_("config.salvar"))

        self.atualizar_resumo_selecionadas()
        self.atualizar_status_conexao(self.conexao_ok, "")
        self.detectar_jogo()

    def criar_pagina_base(self, chave, titulo, descricao):
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(26, 24, 26, 26)
        layout.setSpacing(14)

        titulo_label = QLabel(titulo)
        titulo_label.setStyleSheet("font-size: 21pt; font-weight: 700;")
        layout.addWidget(titulo_label)

        descricao_label = QLabel(descricao)
        descricao_label.setWordWrap(True)
        descricao_label.setStyleSheet("color: #94a3b8;")
        layout.addWidget(descricao_label)

        self.paginas[chave] = pagina
        self.pilha.addWidget(pagina)
        return pagina, layout, titulo_label, descricao_label

    def criar_pagina_inicio(self):
        pagina = QWidget()
        layout = QVBoxLayout(pagina)
        layout.setContentsMargins(26, 24, 26, 26)
        layout.setSpacing(14)

        self.lbl_inicio_titulo = QLabel(_("inicio.titulo"))
        self.lbl_inicio_titulo.setStyleSheet("font-size: 21pt; font-weight: 700;")
        layout.addWidget(self.lbl_inicio_titulo)

        self.lbl_inicio_desc = QLabel(_("inicio.descricao"))
        self.lbl_inicio_desc.setWordWrap(True)
        self.lbl_inicio_desc.setStyleSheet("color: #94a3b8;")
        layout.addWidget(self.lbl_inicio_desc)

        self.banner_widget = BannerL4D()
        layout.addWidget(self.banner_widget)

        painel = QFrame()
        painel.setObjectName("Panel")
        caixa = QVBoxLayout(painel)
        caixa.setContentsMargins(20, 18, 20, 18)
        caixa.setSpacing(12)

        self.lbl_inicio_status = QLabel(_("inicio.status_sistema"))
        caixa.addWidget(self.lbl_inicio_status)

        self.status_jogo = QLabel(_("jogo.verificando"))
        self.status_jogo.setWordWrap(True)
        caixa.addWidget(self.status_jogo)

        self.status_conexao = QLabel(_("conexao.verificando_gamemaps"))
        self.status_conexao.setWordWrap(True)
        caixa.addWidget(self.status_conexao)

        self.local_jogo_label = QLabel(_("jogo.pasta_nao_definida"))
        self.local_jogo_label.setWordWrap(True)
        caixa.addWidget(self.local_jogo_label)

        self.btn_inicio_selecionar = QPushButton(_("inicio.selecionar_pasta"))
        self.btn_inicio_selecionar.clicked.connect(self.selecionar_pasta_jogo)
        caixa.addWidget(self.btn_inicio_selecionar)

        layout.addWidget(painel)

        atalhos = QFrame()
        atalhos.setObjectName("Panel")
        atalhos_layout = QVBoxLayout(atalhos)
        atalhos_layout.setContentsMargins(20, 18, 20, 18)

        self.lbl_inicio_acesso = QLabel(_("inicio.acesso_rapido"))
        atalhos_layout.addWidget(self.lbl_inicio_acesso)

        self.btn_inicio_buscar = QPushButton(_("inicio.buscar_campanhas"))
        self.btn_inicio_buscar.setObjectName("Primary")
        self.btn_inicio_buscar.clicked.connect(lambda: self.mostrar_pagina("buscar"))
        atalhos_layout.addWidget(self.btn_inicio_buscar)

        self.btn_inicio_selecionadas = QPushButton(_("inicio.ver_selecionadas"))
        self.btn_inicio_selecionadas.clicked.connect(
            lambda: self.mostrar_pagina("selecionadas")
        )
        atalhos_layout.addWidget(self.btn_inicio_selecionadas)

        layout.addWidget(atalhos)
        layout.addStretch()

        self.paginas["inicio"] = pagina
        self.pilha.addWidget(pagina)

    def criar_pagina_buscar(self):
        pagina, layout, self.lbl_buscar_titulo, self.lbl_buscar_desc = self.criar_pagina_base(
            "buscar",
            _("busca.titulo"),
            _("busca.descricao"),
        )

        linha = QHBoxLayout()

        self.campo_busca = QLineEdit()
        self.campo_busca.setPlaceholderText(_("busca.placeholder"))
        self.campo_busca.returnPressed.connect(self.iniciar_busca)
        linha.addWidget(self.campo_busca, 1)

        self.botao_buscar = QPushButton(_("busca.pesquisar"))
        self.botao_buscar.setObjectName("Primary")
        self.botao_buscar.clicked.connect(self.iniciar_busca)
        linha.addWidget(self.botao_buscar)

        self.botao_cancelar_busca = QPushButton(_("busca.cancelar"))
        self.botao_cancelar_busca.setEnabled(False)
        self.botao_cancelar_busca.clicked.connect(self.cancelar_busca)
        linha.addWidget(self.botao_cancelar_busca)

        layout.addLayout(linha)

        self.status_busca = QLabel(_("busca.instrucoes"))
        self.status_busca.setWordWrap(True)
        layout.addWidget(self.status_busca)

        corpo = QHBoxLayout()
        corpo.setSpacing(14)

        self.area_resultados = QScrollArea()
        self.area_resultados.setWidgetResizable(True)
        self.area_resultados.setFrameShape(QFrame.Shape.NoFrame)

        self.conteudo_resultados = QWidget()
        self.lista_resultados = QVBoxLayout(self.conteudo_resultados)
        self.lista_resultados.setContentsMargins(2, 2, 8, 2)
        self.lista_resultados.setSpacing(10)
        self.lista_resultados.addStretch()

        self.area_resultados.setWidget(self.conteudo_resultados)
        corpo.addWidget(self.area_resultados, 3)

        painel_lateral = QFrame()
        painel_lateral.setObjectName("Panel")
        painel_lateral.setMinimumWidth(190)
        painel_lateral.setMaximumWidth(250)

        lateral = QVBoxLayout(painel_lateral)
        lateral.setContentsMargins(14, 14, 14, 14)

        self.lbl_buscar_selecao = QLabel(_("busca.sua_selecao"))
        lateral.addWidget(self.lbl_buscar_selecao)

        self.contagem_selecionadas = QLabel(
            _("busca.contagem_selecionadas", quantidade=0)
        )
        self.contagem_selecionadas.setWordWrap(True)
        lateral.addWidget(self.contagem_selecionadas)

        self.area_resumo_selecionadas = QScrollArea()
        self.area_resumo_selecionadas.setWidgetResizable(True)
        self.area_resumo_selecionadas.setFrameShape(QFrame.Shape.NoFrame)
        self.conteudo_resumo_selecionadas = QWidget()
        self.lista_resumo_selecionadas = QVBoxLayout(self.conteudo_resumo_selecionadas)
        self.lista_resumo_selecionadas.setContentsMargins(0, 0, 0, 0)
        self.lista_resumo_selecionadas.setSpacing(6)
        self.area_resumo_selecionadas.setWidget(self.conteudo_resumo_selecionadas)
        lateral.addWidget(self.area_resumo_selecionadas, 1)

        self.botao_baixar_selecionados = QPushButton(_("selecionadas.baixar_instalar"))
        self.botao_baixar_selecionados.setObjectName("Primary")
        self.botao_baixar_selecionados.clicked.connect(self.iniciar_downloads_selecionados)
        lateral.addWidget(self.botao_baixar_selecionados)

        self.botao_remover_selecionados = QPushButton(_("selecionadas.limpar"))
        self.botao_remover_selecionados.clicked.connect(self.remover_todas_selecionadas)
        lateral.addWidget(self.botao_remover_selecionados)

        self.progresso_download = QLabel(_("downloads.nenhum_iniciado"))
        self.progresso_download.setWordWrap(True)
        lateral.addWidget(self.progresso_download)

        self.barra_progresso_lateral = QProgressBar()
        self.barra_progresso_lateral.setRange(0, 100)
        self.barra_progresso_lateral.setValue(0)
        self.barra_progresso_lateral.setFormat("%p% (%v/%m)")
        self.barra_progresso_lateral.setVisible(False)
        lateral.addWidget(self.barra_progresso_lateral)

        self.botao_cancelar_download = QPushButton(_("downloads.cancelar_ativos"))
        self.botao_cancelar_download.setEnabled(False)
        self.botao_cancelar_download.clicked.connect(self.cancelar_downloads)
        lateral.addWidget(self.botao_cancelar_download)

        self.btn_ver_selecionadas = QPushButton(_("busca.gerenciar_selecao"))
        self.btn_ver_selecionadas.clicked.connect(lambda: self.mostrar_pagina("selecionadas"))
        lateral.addWidget(self.btn_ver_selecionadas)

        corpo.addWidget(painel_lateral, 1)
        layout.addLayout(corpo, 1)

    def criar_pagina_selecionadas(self):
        pagina, layout, self.lbl_selec_titulo, self.lbl_selec_desc = self.criar_pagina_base(
            "selecionadas",
            _("selecionadas.titulo"),
            _("selecionadas.descricao"),
        )

        barra = QHBoxLayout()
        barra.setSpacing(12)

        self.contagem_pagina_selecionadas = QLabel(_("selecionadas.vazio"))
        barra.addWidget(self.contagem_pagina_selecionadas, 1)

        coluna_download_verde = QVBoxLayout()
        coluna_download_verde.setContentsMargins(0, 0, 0, 0)
        coluna_download_verde.setSpacing(6)

        self.btn_baixar_todos = QPushButton(_("selecionadas.baixar_instalar"))
        self.btn_baixar_todos.setObjectName("Success")
        self.btn_baixar_todos.clicked.connect(self.iniciar_downloads_selecionados)
        coluna_download_verde.addWidget(self.btn_baixar_todos)

        self.barra_progresso_selecionadas = QProgressBar()
        self.barra_progresso_selecionadas.setRange(0, 100)
        self.barra_progresso_selecionadas.setValue(0)
        self.barra_progresso_selecionadas.setFormat("%p% (%v/%m)")
        self.barra_progresso_selecionadas.setVisible(False)
        coluna_download_verde.addWidget(self.barra_progresso_selecionadas)

        barra.addLayout(coluna_download_verde)

        self.btn_limpar_selecao = QPushButton(_("selecionadas.limpar"))
        self.btn_limpar_selecao.clicked.connect(self.limpar_selecao)
        barra.addWidget(self.btn_limpar_selecao, alignment=Qt.AlignmentFlag.AlignTop)

        layout.addLayout(barra)

        self.area_selecionadas = QScrollArea()
        self.area_selecionadas.setWidgetResizable(True)

        self.conteudo_selecionadas = QWidget()
        self.lista_pagina_selecionadas = QVBoxLayout(self.conteudo_selecionadas)
        self.lista_pagina_selecionadas.addStretch()

        self.area_selecionadas.setWidget(self.conteudo_selecionadas)
        layout.addWidget(self.area_selecionadas, 1)

        self.lbl_selec_aviso = QLabel(_("selecionadas.aviso"))
        self.lbl_selec_aviso.setWordWrap(True)
        self.lbl_selec_aviso.setStyleSheet("color: #60a5fa;")
        layout.addWidget(self.lbl_selec_aviso)

    def criar_pagina_addons(self):
        pagina, layout, self.lbl_addons_titulo, self.lbl_addons_desc = self.criar_pagina_base(
            "addons",
            _("addons.titulo"),
            _("addons.descricao"),
        )

        painel = QFrame()
        painel.setObjectName("Panel")
        caixa = QVBoxLayout(painel)
        caixa.setContentsMargins(20, 18, 20, 18)

        self.addons_caminho = QLabel(_("addons.pasta_nao_identificada"))
        self.addons_caminho.setWordWrap(True)
        caixa.addWidget(self.addons_caminho)

        barra = QHBoxLayout()
        self.btn_addons_abrir = QPushButton(_("addons.abrir_pasta"))
        self.btn_addons_abrir.clicked.connect(self.abrir_pasta_addons)
        barra.addWidget(self.btn_addons_abrir)

        self.btn_addons_atualizar = QPushButton(_("addons.atualizar_lista"))
        self.btn_addons_atualizar.clicked.connect(self.atualizar_lista_addons)
        barra.addWidget(self.btn_addons_atualizar)
        barra.addStretch()
        caixa.addLayout(barra)

        self.lbl_addons_nota = QLabel(_("addons.aviso"))
        self.lbl_addons_nota.setWordWrap(True)
        self.lbl_addons_nota.setStyleSheet("color: #94a3b8;")
        caixa.addWidget(self.lbl_addons_nota)

        layout.addWidget(painel)

        linha_selecao = QHBoxLayout()
        self.addons_contagem = QLabel("")
        linha_selecao.addWidget(self.addons_contagem, 1)
        self.botao_selecionar_todos_addons = QPushButton(_("addons.selecionar_todos"))
        self.botao_selecionar_todos_addons.clicked.connect(self.alternar_selecao_todos_addons)
        linha_selecao.addWidget(self.botao_selecionar_todos_addons)
        self.botao_apagar_addons = QPushButton(_("addons.remover_selecionados"))
        self.botao_apagar_addons.setObjectName("Primary")
        self.botao_apagar_addons.clicked.connect(self.apagar_addons_selecionados)
        linha_selecao.addWidget(self.botao_apagar_addons)
        layout.addLayout(linha_selecao)

        self.area_lista_addons = QScrollArea()
        self.area_lista_addons.setWidgetResizable(True)
        self.area_lista_addons.setFrameShape(QFrame.Shape.NoFrame)
        self.conteudo_lista_addons = QWidget()
        self.lista_addons = QVBoxLayout(self.conteudo_lista_addons)
        self.lista_addons.setContentsMargins(2, 2, 8, 2)
        self.lista_addons.setSpacing(8)
        self.area_lista_addons.setWidget(self.conteudo_lista_addons)
        layout.addWidget(self.area_lista_addons, 1)

    def criar_pagina_configuracoes(self):
        pagina, layout, self.lbl_config_titulo, self.lbl_config_desc = self.criar_pagina_base(
            "config",
            _("config.titulo"),
            _("config.descricao"),
        )

        painel = QFrame()
        painel.setObjectName("Panel")
        formulario = QVBoxLayout(painel)
        formulario.setContentsMargins(20, 18, 20, 18)
        formulario.setSpacing(12)

        self.lbl_config_idioma = QLabel(_("config.idioma"))
        formulario.addWidget(self.lbl_config_idioma)

        self.combo_idioma = QComboBox()
        for codigo, nome in IDIOMAS:
            self.combo_idioma.addItem(nome, codigo)

        indice = self.combo_idioma.findData(self.configuracoes["idioma"])
        self.combo_idioma.setCurrentIndex(max(0, indice))
        formulario.addWidget(self.combo_idioma)

        self.lbl_config_tema = QLabel(_("config.tema"))
        formulario.addWidget(self.lbl_config_tema)

        self.combo_tema = QComboBox()
        self.combo_tema.addItem(_("config.escuro"), "escuro")
        self.combo_tema.addItem(_("config.claro"), "claro")

        indice = self.combo_tema.findData(self.configuracoes["tema"])
        self.combo_tema.setCurrentIndex(max(0, indice))
        formulario.addWidget(self.combo_tema)

        self.lbl_config_downloads = QLabel(_("config.downloads_simultaneos"))
        formulario.addWidget(self.lbl_config_downloads)

        self.spin_downloads = QSpinBox()
        self.spin_downloads.setRange(1, 10)
        self.spin_downloads.setValue(
            self.configuracoes["downloads_simultaneos"]
        )
        formulario.addWidget(self.spin_downloads)

        self.lbl_config_pasta = QLabel(_("config.pasta_jogo"))
        formulario.addWidget(self.lbl_config_pasta)

        linha_pasta = QHBoxLayout()
        self.campo_pasta = QLabel(
            self.pasta_jogo or _("jogo.pasta_nao_definida")
        )
        self.campo_pasta.setWordWrap(True)
        linha_pasta.addWidget(self.campo_pasta, 1)

        self.btn_config_procurar = QPushButton(_("comum.procurar"))
        self.btn_config_procurar.clicked.connect(self.selecionar_pasta_jogo)
        linha_pasta.addWidget(self.btn_config_procurar)
        formulario.addLayout(linha_pasta)

        self.btn_config_salvar = QPushButton(_("config.salvar"))
        self.btn_config_salvar.setObjectName("Primary")
        self.btn_config_salvar.clicked.connect(self.salvar_preferencias)
        formulario.addWidget(self.btn_config_salvar)

        self.mensagem_config = QLabel("")
        self.mensagem_config.setWordWrap(True)
        formulario.addWidget(self.mensagem_config)

        layout.addWidget(painel)
        layout.addStretch()

    def mostrar_pagina(self, chave):
        pagina = self.paginas.get(chave)
        if pagina is None:
            return

        self.pilha.setCurrentWidget(pagina)
        if chave == "addons":
            self.atualizar_lista_addons()

        for nome, botao in self.botoes_navegacao.items():
            botao.setObjectName(
                "NavigationActive" if nome == chave else ""
            )
            botao.style().unpolish(botao)
            botao.style().polish(botao)

    def iniciar_verificacao_conexao(self):
        self.status_conexao.setText(_("conexao.verificando_gamemaps"))
        self.status_sidebar.setText(_("conexao.verificando"))

        self.thread_conexao = QThread(self)
        self.trabalhador_conexao = TrabalhadorConexao()
        self.trabalhador_conexao.moveToThread(self.thread_conexao)

        self.thread_conexao.started.connect(self.trabalhador_conexao.executar)
        self.trabalhador_conexao.terminou.connect(self.atualizar_status_conexao)
        self.trabalhador_conexao.terminou.connect(self.thread_conexao.quit)
        self.thread_conexao.finished.connect(self.trabalhador_conexao.deleteLater)
        self.thread_conexao.finished.connect(self.thread_conexao.deleteLater)
        self.thread_conexao.start()

    def atualizar_status_conexao(self, sucesso, mensagem):
        self.conexao_ok = sucesso

        texto_status = _("conexao.sucesso") if sucesso else _("conexao.falha")
        self.status_conexao.setText("● " + texto_status)

        if sucesso:
            cor = "#22c55e"
            self.status_sidebar.setText(_("conexao.conectado"))
        else:
            cor = "#f87171"
            self.status_sidebar.setText(_("conexao.indisponivel"))

        self.status_conexao.setStyleSheet(f"color: {cor};")
        self.status_sidebar.setStyleSheet(f"color: {cor};")

    def detectar_jogo(self):
        pasta_salva = self.configuracoes.get("pasta_jogo", "")

        if pasta_salva:
            try:
                validada = self.detector.validar_pasta_manual(pasta_salva)
            except Exception:
                validada = None

            if validada:
                self.definir_pasta_jogo(str(validada))
                return

        try:
            pasta = self.detector.localizar_jogo(APP_ID)
        except Exception:
            pasta = None

        if pasta:
            self.definir_pasta_jogo(str(pasta))
        else:
            self.status_jogo.setText(_("jogo.nao_encontrado"))
            self.status_jogo.setStyleSheet("color: #fbbf24;")

    def selecionar_pasta_jogo(self):
        pasta = QFileDialog.getExistingDirectory(
            self,
            _("jogo.selecionar_titulo"),
            self.pasta_jogo or str(Path.home()),
        )

        if not pasta:
            return

        try:
            validada = self.detector.validar_pasta_manual(pasta)
        except Exception:
            validada = None

        if not validada:
            criar_caixa_mensagem(
                self,
                _("jogo.pasta_invalida_titulo"),
                _("jogo.pasta_invalida"),
                QMessageBox.Icon.Warning,
            )
            return

        self.definir_pasta_jogo(str(validada))
        self.salvar_preferencias()

    def definir_pasta_jogo(self, pasta):
        self.pasta_jogo = pasta
        self.configuracoes["pasta_jogo"] = pasta

        self.status_jogo.setText(_("jogo.encontrado"))
        self.status_jogo.setStyleSheet("color: #22c55e;")
        self.local_jogo_label.setText(_("jogo.pasta_atual", pasta=pasta))
        self.campo_pasta.setText(pasta)

        caminho = Path(pasta) / "left4dead" / "addons"
        self.addons_caminho.setText(str(caminho))
        self.atualizar_lista_addons()

    def atualizar_lista_addons(self):
        if not hasattr(self, "lista_addons"):
            return
        while self.lista_addons.count():
            item = self.lista_addons.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.checkboxes_addons.clear()

        if not self.pasta_jogo:
            self.addons_contagem.setText(_("jogo.selecione_primeiro"))
            self.lista_addons.addWidget(QLabel(_("jogo.pasta_nao_definida")))
            self.lista_addons.addStretch()
            return

        pasta = Path(self.pasta_jogo) / "left4dead" / "addons"
        if not pasta.is_dir():
            self.addons_caminho.setText(str(pasta))
            self.addons_contagem.setText(_("addons.pasta_nao_identificada"))
            self.lista_addons.addWidget(QLabel(_("addons.aviso")))
            self.lista_addons.addStretch()
            return

        try:
            arquivos = sorted((item for item in pasta.iterdir() if item.is_file()), key=lambda x: x.name.casefold())
            pastas = sorted((item for item in pasta.iterdir() if item.is_dir()), key=lambda x: x.name.casefold())
        except OSError as erro:
            self.addons_contagem.setText(f"{_('comum.erro')}: {erro}")
            self.lista_addons.addStretch()
            return

        if not arquivos and not pastas:
            self.addons_contagem.setText(_("selecionadas.vazio"))
            self.lista_addons.addWidget(QLabel(_("selecionadas.vazio")))
        else:
            self.addons_contagem.setText(
                _("addons.arquivos_pastas_resumo",
                arquivos=len(arquivos),
                pastas=len(pastas))
            )

            for caminho in arquivos:
                linha = QFrame()
                linha.setObjectName("MapCard")
                caixa = QHBoxLayout(linha)
                check = QCheckBox(caminho.name)
                check.setToolTip(str(caminho))
                caixa.addWidget(check, 1)
                tamanho = caminho.stat().st_size
                caixa.addWidget(QLabel(formatar_tamanho(tamanho)))
                self.checkboxes_addons[str(caminho)] = check
                self.lista_addons.addWidget(linha)

            for caminho in pastas:
                label = QLabel(f"📁 {caminho.name}")
                label.setToolTip(str(caminho))
                self.lista_addons.addWidget(label)
        self.lista_addons.addStretch()

    def alternar_selecao_todos_addons(self):
        if not self.checkboxes_addons:
            return
        marcar = not all(check.isChecked() for check in self.checkboxes_addons.values())
        for check in self.checkboxes_addons.values():
            check.setChecked(marcar)

    def apagar_addons_selecionados(self):
        selecionados = [Path(caminho) for caminho, check in self.checkboxes_addons.items() if check.isChecked()]
        if not selecionados:
            criar_caixa_mensagem(
                self,
                _("comum.erro"),
                _("selecionadas.vazio"),
                QMessageBox.Icon.Information,
            )
            return

        msg = QMessageBox(self)
        msg.setWindowTitle(_("addons.confirmar_remocao_titulo"))
        msg.setText(_("addons.confirmar_remocao", quantidade=len(selecionados)))
        msg.setIcon(QMessageBox.Icon.Warning)

        btn_sim = msg.addButton(_("comum.sim"), QMessageBox.ButtonRole.YesRole)
        msg.addButton(_("comum.nao"), QMessageBox.ButtonRole.NoRole)
        msg.exec()

        if msg.clickedButton() != btn_sim:
            return

        apagados = 0
        falhas = []
        pasta_base = (Path(self.pasta_jogo) / "left4dead" / "addons").resolve()
        for arquivo in selecionados:
            try:
                if arquivo.resolve().parent != pasta_base or not arquivo.is_file():
                    raise OSError(_("addons.caminho_invalido"))
                arquivo.unlink()
                apagados += 1
            except OSError as erro:
                falhas.append(f"{arquivo.name}: {erro}")
        self.atualizar_lista_addons()

        mensagem = _("addons.arquivos_apagados", quantidade=apagados)
        if falhas:
            mensagem += "\n\n" + _("addons.falhas_titulo") + "\n" + "\n".join(falhas[:10])

        criar_caixa_mensagem(self, _("app.nome"), mensagem, QMessageBox.Icon.Information)

    def abrir_pasta_addons(self):
        if not self.pasta_jogo:
            criar_caixa_mensagem(
                self,
                _("jogo.nao_encontrado_titulo"),
                _("jogo.selecione_primeiro"),
                QMessageBox.Icon.Information,
            )
            return

        pasta_addons = Path(self.pasta_jogo) / "left4dead" / "addons"

        if not pasta_addons.is_dir():
            btn_clicado = criar_caixa_mensagem(
                self,
                _("addons.criar_titulo"),
                _("addons.criar_pergunta", pasta=str(pasta_addons)),
                QMessageBox.Icon.Question,
                [(_("comum.sim"), QMessageBox.ButtonRole.YesRole), (_("comum.nao"), QMessageBox.ButtonRole.NoRole)],
            )

            if btn_clicado.text() != _("comum.sim"):
                return

            try:
                pasta_addons.mkdir(parents=True, exist_ok=True)
            except OSError as erro:
                criar_caixa_mensagem(
                    self,
                    _("comum.erro"),
                    _("addons.criar_erro", erro=str(erro)),
                    QMessageBox.Icon.Critical,
                )
                return

        try:
            if sys.platform == "win32":
                os.startfile(str(pasta_addons))
            else:
                subprocess.Popen(["xdg-open", str(pasta_addons)])
        except (OSError, AttributeError) as erro:
            criar_caixa_mensagem(
                self,
                _("comum.erro"),
                _("addons.abrir_erro", erro=str(erro)),
                QMessageBox.Icon.Warning,
            )

    def iniciar_busca(self):
        termo = self.campo_busca.text().strip()

        if not termo:
            self.status_busca.setText(_("busca.digite_termo"))
            return

        self.id_busca_atual += 1
        id_busca = self.id_busca_atual

        self.limpar_resultados_visuais()
        self.resultados_atuais = []
        self.status_busca.setText(f"{_('busca.iniciando')} ({termo})")

        self.botao_buscar.setEnabled(True)
        self.botao_cancelar_busca.setEnabled(True)

        cancelar = Event()
        thread = QThread(self)
        trabalhador = TrabalhadorBusca(id_busca, termo, cancelar)
        trabalhador.moveToThread(thread)

        registro = {
            "id": id_busca,
            "termo": termo,
            "cancelar": cancelar,
            "thread": thread,
            "trabalhador": trabalhador,
        }
        self.threads_busca_ativas.append(registro)

        thread.started.connect(trabalhador.executar)
        trabalhador.progresso.connect(self.atualizar_progresso_busca_identificada)
        trabalhador.terminou.connect(self.finalizar_busca_identificada)
        trabalhador.falha.connect(self.exibir_erro_busca_identificada)
        trabalhador.terminou.connect(lambda *_: thread.quit())

        thread.finished.connect(trabalhador.deleteLater)
        thread.finished.connect(lambda r=registro: self.remover_busca_finalizada(r))
        thread.finished.connect(thread.deleteLater)

        self.thread_busca = thread
        self.trabalhador_busca = trabalhador
        self.cancelamento_busca = cancelar

        thread.start()

    def atualizar_progresso_busca_identificada(self, id_busca, termo, pagina, total):
        if id_busca != self.id_busca_atual:
            return
        self.status_busca.setText(_("busca.progresso", pagina=pagina, total=total))

    def finalizar_busca_identificada(self, id_busca, termo, resultados, cancelada):
        if id_busca != self.id_busca_atual:
            return

        resultados = resultados or []
        self.resultados_atuais = resultados
        self.mostrar_resultados(resultados)

        if cancelada:
            mensagem = _("busca.cancelada", quantidade=len(resultados))
        else:
            mensagem = _("busca.concluida", quantidade=len(resultados))

        self.status_busca.setText(mensagem)
        self.botao_buscar.setEnabled(True)
        self.botao_cancelar_busca.setEnabled(False)

    def exibir_erro_busca_identificada(self, id_busca, termo, erro):
        if id_busca != self.id_busca_atual:
            return
        self.status_busca.setText(_("busca.erro", erro=erro))

    def remover_busca_finalizada(self, registro):
        if registro in self.threads_busca_ativas:
            self.threads_busca_ativas.remove(registro)

        if self.cancelamento_busca is registro["cancelar"]:
            buscas_ativas = [r for r in self.threads_busca_ativas if r["id"] == self.id_busca_atual]
            if not buscas_ativas:
                self.botao_cancelar_busca.setEnabled(False)

    def cancelar_busca(self):
        if self.cancelamento_busca is not None:
            self.cancelamento_busca.set()
            self.status_busca.setText(_("busca.cancelando"))
            self.botao_cancelar_busca.setEnabled(False)

    def limpar_resultados_visuais(self):
        while self.lista_resultados.count():
            item = self.lista_resultados.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.cartoes.clear()

    def mostrar_resultados(self, resultados):
        self.limpar_resultados_visuais()

        if not resultados:
            vazio = QLabel(_("busca.nenhum_resultado"))
            vazio.setWordWrap(True)
            self.lista_resultados.addWidget(vazio)
            self.lista_resultados.addStretch()
            return

        for campanha in resultados:
            url = campanha.get("url")
            if not url:
                continue

            cartao = CartaoCampanha(
                campanha,
                selecionada=url in self.campanhas_selecionadas,
            )
            cartao.alteracao_selecao.connect(self.alterar_selecao)
            self.lista_resultados.addWidget(cartao)
            self.cartoes.append(cartao)

        self.lista_resultados.addStretch()

    def alterar_selecao(self, campanha, selecionada):
        url = campanha.get("url")
        if not url:
            return

        if selecionada:
            self.campanhas_selecionadas[url] = campanha
        else:
            self.campanhas_selecionadas.pop(url, None)

        self.atualizar_resumo_selecionadas()

    def atualizar_resumo_selecionadas(self):
        quantidade = len(self.campanhas_selecionadas)
        texto_contagem = _("busca.contagem_selecionadas", quantidade=quantidade)
        self.contagem_selecionadas.setText(texto_contagem)
        self.contagem_pagina_selecionadas.setText(texto_contagem)

        while self.lista_resumo_selecionadas.count():
            item = self.lista_resumo_selecionadas.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.campanhas_selecionadas:
            vazio = QLabel(_("busca.resumo_vazio"))
            vazio.setWordWrap(True)
            self.lista_resumo_selecionadas.addWidget(vazio)
        else:
            for url, campanha in self.campanhas_selecionadas.items():
                linha = QFrame()
                linha.setObjectName("MapCard")
                caixa = QHBoxLayout(linha)
                caixa.setContentsMargins(7, 6, 7, 6)
                nome = QLabel(campanha.get("nome") or _("busca.campanha_sem_nome"))
                nome.setWordWrap(True)
                nome.setMinimumWidth(0)
                caixa.addWidget(nome, 1)
                remover = QPushButton("×")
                remover.setFixedWidth(30)
                remover.clicked.connect(lambda _checked=False, destino=url: self.remover_selecionada(destino))
                caixa.addWidget(remover)
                self.lista_resumo_selecionadas.addWidget(linha)
        self.lista_resumo_selecionadas.addStretch()
        self.atualizar_lista_selecionadas()

    def confirmar_limpeza_selecao(self):
        if not self.campanhas_selecionadas:
            return False

        msg = QMessageBox(self)
        msg.setWindowTitle(_("selecionadas.limpar"))
        msg.setText(_("selecionadas.confirmar_limpeza"))
        msg.setIcon(QMessageBox.Icon.Question)

        btn_sim = msg.addButton(_("comum.sim"), QMessageBox.ButtonRole.YesRole)
        msg.addButton(_("comum.nao"), QMessageBox.ButtonRole.NoRole)
        msg.exec()

        if msg.clickedButton() != btn_sim:
            return False

        self.campanhas_selecionadas.clear()
        for cartao in self.cartoes:
            cartao.checkbox.blockSignals(True)
            cartao.checkbox.setChecked(False)
            cartao.checkbox.blockSignals(False)

        self.atualizar_resumo_selecionadas()
        return True

    def remover_todas_selecionadas(self):
        self.confirmar_limpeza_selecao()

    def limpar_selecao(self):
        self.confirmar_limpeza_selecao()

    def iniciar_downloads_selecionados(self):
        if not self.campanhas_selecionadas:
            criar_caixa_mensagem(
                self,
                _("download.nenhuma_campanha_titulo"),
                _("download.selecione_uma"),
                QMessageBox.Icon.Information,
            )
            return

        if not self.pasta_jogo or not Path(self.pasta_jogo).is_dir():
            criar_caixa_mensagem(
                self,
                _("jogo.pasta_necessaria_titulo"),
                _("jogo.pasta_necessaria"),
                QMessageBox.Icon.Warning,
            )
            return

        self.botao_baixar_selecionados.setEnabled(False)
        self.btn_baixar_todos.setEnabled(False)
        self.botao_cancelar_download.setEnabled(True)
        self.progresso_download.setText(_("downloads.preparando"))
        
        self._progresso_downloads_cache.clear()
        self.barra_progresso_lateral.setVisible(True)
        self.barra_progresso_lateral.setRange(0, 100)
        self.barra_progresso_lateral.setValue(0)
        
        self.barra_progresso_selecionadas.setVisible(True)
        self.barra_progresso_selecionadas.setRange(0, 100)
        self.barra_progresso_selecionadas.setValue(0)

        def preparar_e_enfileirar():
            for url_pagina, campanha in list(self.campanhas_selecionadas.items()):
                nome = campanha.get("nome") or _("busca.campanha_sem_nome")
                try:
                    url_download = obter_link_download(url_pagina)
                    if url_download:
                        self.gerenciador_downloads.adicionar(
                            identificador=url_pagina,
                            url=url_download,
                            nome=nome,
                            pasta_jogo=self.pasta_jogo,
                            referer=url_pagina,
                            instalar=True,
                        )
                    else:
                        self.ao_atualizar_mensagem_download(
                            url_pagina, _("downloads.nao_obter_link", mensagem=nome)
                        )
                except Exception as e:
                    self.ao_atualizar_mensagem_download(url_pagina, str(e))

        threading.Thread(target=preparar_e_enfileirar, daemon=True).start()

    def ao_atualizar_mensagem_download(self, identificador, mensagem):
        self.progresso_download.setText(mensagem)

    def ao_atualizar_progresso_download(self, identificador, baixado, total, percentual):
        self._progresso_downloads_cache[identificador] = (baixado, total, percentual)

        baixado_total = sum(item[0] for item in self._progresso_downloads_cache.values())
        tamanho_total = sum(item[1] for item in self._progresso_downloads_cache.values())
        
        if tamanho_total > 0:
            percentual_geral = min(100, int((baixado_total / tamanho_total) * 100))
        else:
            percentual_geral = percentual

        agora = time.monotonic()
        if agora - self._ultimo_update_progresso < 0.08 and percentual_geral < 100:
            return
        self._ultimo_update_progresso = agora

        if tamanho_total > 0:
            texto = _("downloads.baixado", baixado=formatar_tamanho(baixado_total), total=formatar_tamanho(tamanho_total), percentual=percentual_geral)
            formato_str = f"%p% ({formatar_tamanho(baixado_total)} / {formatar_tamanho(tamanho_total)})"
        else:
            texto = _("downloads.baixado_sem_total", baixado=formatar_tamanho(baixado), percentual=percentual)
            formato_str = f"%p% ({formatar_tamanho(baixado)})"

        self.progresso_download.setText(texto)
        
        QMetaObject.invokeMethod(self.barra_progresso_lateral, "setValue", Qt.ConnectionType.QueuedConnection, Q_ARG(int, percentual_geral))
        QMetaObject.invokeMethod(self.barra_progresso_lateral, "setFormat", Qt.ConnectionType.QueuedConnection, Q_ARG(str, formato_str))

        QMetaObject.invokeMethod(self.barra_progresso_selecionadas, "setValue", Qt.ConnectionType.QueuedConnection, Q_ARG(int, percentual_geral))
        QMetaObject.invokeMethod(self.barra_progresso_selecionadas, "setFormat", Qt.ConnectionType.QueuedConnection, Q_ARG(str, formato_str))

    @Slot()
    def _exibir_pop_in_sucesso(self):
        pasta_addons = Path(self.pasta_jogo) / "left4dead" / "addons" if self.pasta_jogo else Path("left4dead/addons")
        dialogo = DialogoPopInSucesso(self, _("downloads.sucesso_instalacao_detalhe", pasta=pasta_addons))
        dialogo.exec()

    def ao_concluir_download(self, identificador, sucesso, mensagem):
        self.atualizar_lista_addons()
        
        tarefas = self.gerenciador_downloads.listar_tarefas()
        ativas = any(t.get("estado") in ("Na fila", "Baixando") for t in tarefas.values())
        if not ativas:
            self.botao_baixar_selecionados.setEnabled(True)
            self.btn_baixar_todos.setEnabled(True)
            self.botao_cancelar_download.setEnabled(False)
            
            QMetaObject.invokeMethod(self, "_exibir_pop_in_sucesso", Qt.ConnectionType.QueuedConnection)

    def cancelar_downloads(self):
        self.gerenciador_downloads.cancelar_todos()
        self.progresso_download.setText(_("downloads.cancelamento_solicitado"))
        self.botao_cancelar_download.setEnabled(False)
        self.botao_baixar_selecionados.setEnabled(True)
        self.btn_baixar_todos.setEnabled(True)
        self.barra_progresso_lateral.setVisible(False)
        self.barra_progresso_selecionadas.setVisible(False)

    def atualizar_lista_selecionadas(self):
        while self.lista_pagina_selecionadas.count():
            item = self.lista_pagina_selecionadas.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not self.campanhas_selecionadas:
            vazio = QLabel(_("selecionadas.vazio"))
            self.lista_pagina_selecionadas.addWidget(vazio)
        else:
            for url, campanha in self.campanhas_selecionadas.items():
                linha = QFrame()
                linha.setObjectName("MapCard")
                caixa = QHBoxLayout(linha)

                nome = QLabel(campanha.get("nome", _("busca.campanha_sem_nome")))
                nome.setWordWrap(True)
                caixa.addWidget(nome, 1)

                abrir = QPushButton(_("selecionadas.abrir"))
                abrir.clicked.connect(
                    lambda _checked=False, destino=url:
                    QDesktopServices.openUrl(QUrl(destino))
                )
                caixa.addWidget(abrir)

                remover = QPushButton(_("selecionadas.remover"))
                remover.clicked.connect(
                    lambda _checked=False, destino=url:
                    self.remover_selecionada(destino)
                )
                caixa.addWidget(remover)

                self.lista_pagina_selecionadas.addWidget(linha)

        self.lista_pagina_selecionadas.addStretch()

    def remover_selecionada(self, url):
        self.campanhas_selecionadas.pop(url, None)
        self.atualizar_resumo_selecionadas()

        for cartao in self.cartoes:
            if cartao.campanha.get("url") == url:
                cartao.checkbox.blockSignals(True)
                cartao.checkbox.setChecked(False)
                cartao.checkbox.blockSignals(False)

    def salvar_preferencias(self):
        idioma_anterior = self.configuracoes["idioma"]

        self.configuracoes["idioma"] = self.combo_idioma.currentData()
        self.configuracoes["tema"] = self.combo_tema.currentData()
        self.configuracoes["downloads_simultaneos"] = self.spin_downloads.value()
        self.configuracoes["pasta_jogo"] = self.pasta_jogo

        self.gerenciador_downloads.definir_limite(self.configuracoes["downloads_simultaneos"])

        if not salvar_configuracoes(self.configuracoes):
            self.mensagem_config.setText(_("config.erro_salvar"))
            self.mensagem_config.setStyleSheet("color: #f87171;")
            return

        aplicar_tema(QApplication.instance(), self.configuracoes["tema"])

        try:
            definir_idioma(self.configuracoes["idioma"])
        except Exception:
            definir_idioma("pt_BR")

        if idioma_anterior != self.configuracoes["idioma"]:
            self.retraduzir_interface()

        mensagem = _("config.salvo")
        self.mensagem_config.setText(mensagem)
        self.mensagem_config.setStyleSheet("color: #22c55e;")

    def closeEvent(self, evento):
        if self.cancelamento_busca is not None:
            self.cancelamento_busca.set()

        tarefas = self.gerenciador_downloads.listar_tarefas()
        ativas = any(t.get("estado") in ("Na fila", "Baixando") for t in tarefas.values())

        if ativas:
            resp = criar_caixa_mensagem(
                self,
                _("janela.atividades_em_andamento"),
                _("janela.confirmar_fechamento"),
                QMessageBox.Icon.Question,
                [(_("comum.sim"), QMessageBox.ButtonRole.YesRole), (_("comum.nao"), QMessageBox.ButtonRole.NoRole)],
            )
            if resp.text() != _("comum.sim"):
                evento.ignore()
                return

        self.gerenciador_downloads.encerrar(aguardar=False)

        if self.thread_busca and self.thread_busca.isRunning():
            self.thread_busca.quit()
            self.thread_busca.wait(1000)

        evento.accept()


def main():
    aplicativo = QApplication(sys.argv)
    aplicativo.setApplicationName("L4D Map Downloader")

    primeira_execucao = not ARQUIVO_CONFIG.exists()
    configuracoes = carregar_configuracoes()

    if primeira_execucao:
        definir_idioma("pt_BR")
        janela_idioma = JanelaEscolhaIdioma()
        if janela_idioma.exec() == QDialog.DialogCode.Accepted:
            configuracoes["idioma"] = janela_idioma.idioma_selecionado
            salvar_configuracoes(configuracoes)

    try:
        definir_idioma(configuracoes["idioma"])
    except Exception:
        definir_idioma("pt_BR")

    aplicar_tema(aplicativo, configuracoes["tema"])

    janela = JanelaPrincipal(configuracoes)
    janela.show()

    sys.exit(aplicativo.exec())


def main_cli():
    main()


if __name__ == "__main__":
    main()
