from __future__ import annotations
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlparse
import requests
from idiomas import _


TIMEOUT = 60
TIMEOUT_EXTRACAO = 600
TAMANHO_BLOCO = 128 * 1024
PASTA_DOWNLOADS = "L4D Map Downloader"

EXTENSOES_ARQUIVOS = (
    ".zip", ".rar", ".7z", ".vpk", ".tar", ".gz", ".bz2"
)

CallbackProgresso = Optional[Callable[[int, int, int], None]]
CallbackMensagem = Optional[Callable[[str], None]]

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

_LOCKS_INSTALACAO: dict[str, threading.RLock] = {}
_LOCKS_INSTALACAO_MUTEX = threading.Lock()


def formatar_tamanho(tamanho: int | float) -> str:
    tamanho = max(0.0, float(tamanho))

    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if tamanho < 1024 or unidade == "TB":
            return (
                f"{int(tamanho)} {unidade}"
                if unidade == "B"
                else f"{tamanho:.2f} {unidade}"
            )
        tamanho /= 1024

    return f"{tamanho:.2f} TB"


def nome_seguro(nome: str) -> str:
    nome = os.path.basename(nome.strip())
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nome).rstrip(". ")
    return (nome if nome and nome not in (".", "..") else "download")[:180]


def obter_pasta_downloads() -> str:
    pasta = Path.home() / "Downloads" / PASTA_DOWNLOADS
    pasta.mkdir(parents=True, exist_ok=True)
    return str(pasta)


def localizar_winrar() -> Optional[str]:
    candidatos = (
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "WinRAR" / "WinRAR.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "WinRAR" / "Rar.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "WinRAR" / "WinRAR.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "WinRAR" / "Rar.exe",
    )

    for caminho in candidatos:
        if caminho.is_file():
            return str(caminho)

    return shutil.which("WinRAR") or shutil.which("Rar")


def nome_do_download(url: str, nome_sugerido: Optional[str] = None) -> str:
    nome_url = os.path.basename(unquote(urlparse(url).path))

    if nome_url and "." in nome_url:
        return nome_seguro(nome_url)

    sugerido = nome_seguro(nome_sugerido or "mapa")
    return (
        sugerido
        if Path(sugerido).suffix.lower() in EXTENSOES_ARQUIVOS
        else f"{sugerido}.zip"
    )


def _mensagem(callback: CallbackMensagem, texto: str) -> None:
    if callback:
        try:
            callback(texto)
        except Exception:
            pass


def _progresso(
    callback: CallbackProgresso,
    baixado: int,
    total: int,
    percentual: int,
) -> None:
    if callback:
        try:
            callback(baixado, total, percentual)
        except Exception:
            pass


def _verificar_cancelamento(cancelar: Optional[threading.Event]) -> None:
    if cancelar and cancelar.is_set():
        raise InterruptedError(_("downloads.cancelamento_solicitado"))


def _reservar_destino(pasta: Path, nome: str) -> Path:
    caminho = pasta / nome
    contador = 1

    while caminho.exists():
        caminho = pasta / f"{Path(nome).stem} ({contador}){Path(nome).suffix}"
        contador += 1

    return caminho


def baixar_arquivo(
    url: str,
    destino: str,
    nome_sugerido: Optional[str] = None,
    referer: Optional[str] = None,
    callback_progresso: CallbackProgresso = None,
    callback_mensagem: CallbackMensagem = None,
    cancelar: Optional[threading.Event] = None,
    timeout: int = TIMEOUT,
) -> Optional[str]:
    temporario: Optional[Path] = None

    try:
        _verificar_cancelamento(cancelar)

        pasta = Path(destino)
        pasta.mkdir(parents=True, exist_ok=True)
        nome = nome_do_download(url, nome_sugerido)

        fd, caminho_temp = tempfile.mkstemp(
            prefix=f"{Path(nome).stem}_",
            suffix=".part",
            dir=str(pasta),
        )
        os.close(fd)
        temporario = Path(caminho_temp)

        cabecalhos = {"User-Agent": _USER_AGENT}
        if referer:
            cabecalhos["Referer"] = referer

        _mensagem(callback_mensagem, _("downloads.preparando") + f": {nome}")

        baixado = 0
        total = 0
        ultimo_evento = 0.0

        with requests.get(
            url,
            headers=cabecalhos,
            stream=True,
            timeout=(15, timeout),
            allow_redirects=True,
        ) as resposta:
            resposta.raise_for_status()

            tipo = resposta.headers.get("Content-Type", "").lower()
            if "text/html" in tipo or "application/xhtml" in tipo:
                raise ValueError(_("downloads.link_indisponivel"))

            try:
                total = int(resposta.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                total = 0

            with temporario.open("wb") as arquivo:
                for bloco in resposta.iter_content(TAMANHO_BLOCO):
                    _verificar_cancelamento(cancelar)
                    if not bloco:
                        continue

                    arquivo.write(bloco)
                    baixado += len(bloco)

                    agora = time.monotonic()
                    if agora - ultimo_evento >= 0.15:
                        percentual = min(100, int(baixado * 100 / total)) if total else 0
                        _progresso(callback_progresso, baixado, total, percentual)
                        ultimo_evento = agora

        _verificar_cancelamento(cancelar)

        if baixado <= 0:
            raise ValueError(_("instalacao.arquivo_vazio"))

        if total and baixado != total:
            raise IOError(
                _("downloads.incompleto", baixado=formatar_tamanho(baixado), total=formatar_tamanho(total))
            )

        with threading.Lock():
            destino_final = _reservar_destino(pasta, nome)
            os.replace(temporario, destino_final)

        temporario = None
        _progresso(callback_progresso, baixado, total or baixado, 100)
        _mensagem(
            callback_mensagem,
            _("downloads.status_concluido", mensagem=destino_final.name),
        )
        return str(destino_final)

    except InterruptedError:
        _mensagem(callback_mensagem, _("downloads.cancelamento_solicitado"))
        return None
    except Exception as erro:
        _mensagem(callback_mensagem, _("downloads.erro", mensagem=str(erro)))
        return None
    finally:
        if temporario:
            try:
                temporario.unlink(missing_ok=True)
            except OSError:
                pass


def copiar_arquivos_extraidos(
    origem: str,
    destino: str,
    cancelar: Optional[threading.Event] = None,
) -> int:
    origem_path = Path(origem).resolve()
    destino_path = Path(destino).resolve()

    if not origem_path.is_dir():
        raise FileNotFoundError(
            _("instalacao.pasta_origem_inexistente", pasta=str(origem_path))
        )

    destino_path.mkdir(parents=True, exist_ok=True)
    copiados = 0

    for raiz, diretorios, arquivos in os.walk(origem_path):
        _verificar_cancelamento(cancelar)
        diretorios[:] = [d for d in diretorios if d != "__MACOSX"]

        pasta_origem = Path(raiz)
        relativo = pasta_origem.relative_to(origem_path)
        pasta_destino = (destino_path / relativo).resolve()

        if not pasta_destino.is_relative_to(destino_path):
            raise ValueError(_("instalacao.caminho_extracao_invalido"))

        pasta_destino.mkdir(parents=True, exist_ok=True)

        for nome in arquivos:
            _verificar_cancelamento(cancelar)
            origem_arquivo = pasta_origem / nome
            destino_arquivo = (pasta_destino / nome).resolve()

            if not destino_arquivo.is_relative_to(destino_path):
                raise ValueError(_("instalacao.arquivo_fora_pasta"))

            try:
                shutil.copy2(origem_arquivo, destino_arquivo)
                copiados += 1
            except OSError as erro:
                raise OSError(
                    _("instalacao.erro_copiar_arquivo",
                      arquivo=str(destino_arquivo), erro=str(erro))
                ) from erro

    return copiados


def _executar_winrar_silencioso(
    comando: list[str],
    cancelar: Optional[threading.Event] = None,
) -> tuple[int, str]:
    opcoes = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.PIPE,
        "text": True,
        "errors": "replace",
    }

    if os.name == "nt":
        opcoes["creationflags"] = subprocess.CREATE_NO_WINDOW
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        opcoes["startupinfo"] = startup

    processo = subprocess.Popen(comando, **opcoes)
    inicio = time.monotonic()

    while processo.poll() is None:
        if cancelar and cancelar.is_set():
            processo.terminate()
            try:
                processo.wait(timeout=5)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait()
            raise InterruptedError(_("downloads.cancelamento_solicitado"))

        if time.monotonic() - inicio > TIMEOUT_EXTRACAO:
            processo.kill()
            processo.wait()
            raise TimeoutError(_("instalacao.tempo_limite_extracao"))

        time.sleep(0.2)

    detalhes = processo.stderr.read().strip() if processo.stderr else ""
    return processo.returncode, detalhes


def extrair_seguro(
    arquivo: str,
    destino: str,
    winrar: Optional[str] = None,
    cancelar: Optional[threading.Event] = None,
    callback_mensagem: CallbackMensagem = None,
) -> bool:
    caminho = Path(arquivo)

    if not caminho.is_file():
        _mensagem(
            callback_mensagem,
            _("downloads.erro", mensagem=_("instalacao.arquivo_inexistente")),
        )
        return False

    if caminho.suffix.lower() == ".vpk":
        _mensagem(callback_mensagem, _("instalacao.arquivo_ja_vpk"))
        return False

    executavel = winrar or localizar_winrar()
    if not executavel:
        _mensagem(callback_mensagem, _("instalacao.winrar_nao_encontrado"))
        return False

    try:
        _verificar_cancelamento(cancelar)

        with tempfile.TemporaryDirectory(prefix="l4d_extracao_") as temporario:
            pasta_temp = Path(temporario)
            comando = [
                executavel, "x", "-ibck", "-y", "-o+",
                str(caminho), str(pasta_temp) + os.sep,
            ]

            _mensagem(
                callback_mensagem,
                _("instalacao.extraindo", arquivo=caminho.name),
            )
            codigo, detalhes = _executar_winrar_silencioso(comando, cancelar)

            if codigo != 0:
                raise RuntimeError(
                    detalhes or _("instalacao.erro_winrar", codigo=codigo)
                )

            _verificar_cancelamento(cancelar)

            if not any(p.is_file() for p in pasta_temp.rglob("*")):
                _mensagem(
                    callback_mensagem,
                    _("downloads.erro",
                      mensagem=_("instalacao.nenhum_arquivo_instalar")),
                )
                return False

            quantidade = copiar_arquivos_extraidos(
                str(pasta_temp), destino, cancelar
            )

            if quantidade <= 0:
                _mensagem(
                    callback_mensagem,
                    _("downloads.erro",
                      mensagem=_("instalacao.nenhum_arquivo_copiado")),
                )
                return False

            _mensagem(
                callback_mensagem,
                _("downloads.status_concluido", mensagem=str(destino)),
            )
            return True

    except InterruptedError:
        _mensagem(callback_mensagem, _("downloads.cancelamento_solicitado"))
        return False
    except Exception as erro:
        _mensagem(callback_mensagem, _("downloads.erro", mensagem=str(erro)))
        return False


def _localizar_pasta_addons(pasta_jogo: Path) -> Optional[Path]:
    pasta_jogo = pasta_jogo.resolve()

    if pasta_jogo.name.lower() in ("left4dead", "left4dead2"):
        return pasta_jogo / "addons"

    for nome in ("left4dead", "left4dead2"):
        candidato = pasta_jogo / nome / "addons"
        if candidato.parent.is_dir():
            return candidato

    return None


def instalar_conteudo(
    arquivo: str,
    pasta_jogo: str,
    cancelar: Optional[threading.Event] = None,
    callback_mensagem: CallbackMensagem = None,
) -> bool:
    try:
        _verificar_cancelamento(cancelar)

        caminho = Path(arquivo).resolve()
        jogo = Path(pasta_jogo).resolve()

        if not caminho.is_file():
            _mensagem(
                callback_mensagem,
                _("downloads.erro", mensagem=_("instalacao.arquivo_nao_encontrado")),
            )
            return False

        if not jogo.is_dir():
            _mensagem(callback_mensagem, _("jogo.pasta_invalida"))
            return False

        pasta_addons = _localizar_pasta_addons(jogo)
        if pasta_addons is None:
            _mensagem(callback_mensagem, _("jogo.pasta_invalida"))
            return False

        extensao = caminho.suffix.lower()
        if extensao not in EXTENSOES_ARQUIVOS:
            _mensagem(
                callback_mensagem,
                _("downloads.erro", mensagem=_(
                    "instalacao.formato_nao_suportado", formato=extensao
                )),
            )
            return False

        pasta_addons.mkdir(parents=True, exist_ok=True)
        chave = str(pasta_addons.resolve()).casefold()

        with _LOCKS_INSTALACAO_MUTEX:
            lock = _LOCKS_INSTALACAO.setdefault(chave, threading.RLock())

        with lock:
            _verificar_cancelamento(cancelar)

            if extensao == ".vpk":
                destino = pasta_addons / caminho.name
                shutil.copy2(caminho, destino)
                _mensagem(
                    callback_mensagem,
                    _("downloads.status_concluido", mensagem=destino.name),
                )
                return True

            return extrair_seguro(
                str(caminho),
                str(pasta_addons),
                cancelar=cancelar,
                callback_mensagem=callback_mensagem,
            )

    except InterruptedError:
        _mensagem(callback_mensagem, _("downloads.cancelamento_solicitado"))
        return False
    except Exception as erro:
        _mensagem(callback_mensagem, _("downloads.erro", mensagem=str(erro)))
        return False


def baixar_e_instalar(
    url: str,
    nome: str,
    pasta_jogo: str,
    referer: Optional[str] = None,
    callback_progresso: CallbackProgresso = None,
    callback_mensagem: CallbackMensagem = None,
    cancelar: Optional[threading.Event] = None,
    instalar: bool = True,
) -> bool:
    arquivo = baixar_arquivo(
        url=url,
        destino=obter_pasta_downloads(),
        nome_sugerido=nome,
        referer=referer,
        callback_progresso=callback_progresso,
        callback_mensagem=callback_mensagem,
        cancelar=cancelar,
    )

    if not arquivo:
        return False

    if cancelar and cancelar.is_set():
        return False

    return (
        instalar_conteudo(
            arquivo, pasta_jogo, cancelar, callback_mensagem
        )
        if instalar else True
    )


class GerenciadorDownloads:
    ESTADOS_FINAIS = {"Concluído", "Falhou", "Cancelado"}

    def __init__(
        self,
        downloads_simultaneos: int = 3,
        on_progresso=None,
        on_mensagem=None,
        on_concluido=None,
    ):
        self._lock = threading.RLock()
        self._tarefas: dict[str, dict] = {}
        self._cancelamentos: dict[str, threading.Event] = {}
        self._futuros: dict[str, Future] = {}

        self.on_progresso = on_progresso
        self.on_mensagem = on_mensagem
        self.on_concluido = on_concluido
        self._limite = max(1, min(10, int(downloads_simultaneos)))
        self._executor = ThreadPoolExecutor(
            max_workers=self._limite,
            thread_name_prefix="L4DDownload",
        )

    @property
    def limite(self) -> int:
        return self._limite

    def definir_limite(self, quantidade: int) -> None:
        quantidade = max(1, min(10, int(quantidade)))

        with self._lock:
            if quantidade == self._limite:
                return

            antigo = self._executor
            self._limite = quantidade
            self._executor = ThreadPoolExecutor(
                max_workers=quantidade,
                thread_name_prefix="L4DDownload",
            )
            antigo.shutdown(wait=False, cancel_futures=False)

    def listar_tarefas(self) -> dict:
        with self._lock:
            return {
                chave: {
                    k: v for k, v in tarefa.items()
                    if k != "future"
                }
                for chave, tarefa in self._tarefas.items()
            }

    def adicionar(
        self,
        identificador: str,
        url: str,
        nome: str,
        pasta_jogo: str,
        referer: Optional[str] = None,
        instalar: bool = True,
    ) -> Future:
        identificador = str(identificador)

        with self._lock:
            if identificador in self._tarefas:
                raise ValueError(
                    _("downloads.id_duplicado", identificador=identificador)
                )

            cancelar = threading.Event()
            self._cancelamentos[identificador] = cancelar
            self._tarefas[identificador] = {
                "id": identificador,
                "nome": nome,
                "url": url,
                "estado": "Na fila",
                "progresso": 0,
                "baixado": 0,
                "total": 0,
                "sucesso": None,
                "mensagem": _("downloads.link_encontrado"),
            }

            futuro = self._executor.submit(
                self._executar_tarefa,
                identificador, url, nome, pasta_jogo,
                referer, instalar, cancelar,
            )
            self._futuros[identificador] = futuro
            self._tarefas[identificador]["future"] = futuro
            return futuro

    def _atualizar(self, identificador: str, **valores) -> None:
        with self._lock:
            if identificador in self._tarefas:
                self._tarefas[identificador].update(valores)

    def _mensagem(self, identificador: str, mensagem: str) -> None:
        self._atualizar(identificador, mensagem=mensagem)
        if self.on_mensagem:
            try:
                self.on_mensagem(identificador, mensagem)
            except Exception:
                pass

    def _progresso(
        self, identificador: str, baixado: int, total: int, percentual: int
    ) -> None:
        self._atualizar(
            identificador,
            baixado=baixado,
            total=total,
            progresso=percentual,
        )
        if self.on_progresso:
            try:
                self.on_progresso(identificador, baixado, total, percentual)
            except Exception:
                pass

    def _executar_tarefa(
        self,
        identificador: str,
        url: str,
        nome: str,
        pasta_jogo: str,
        referer: Optional[str],
        instalar: bool,
        cancelar: threading.Event,
    ) -> bool:
        self._atualizar(
            identificador,
            estado="Baixando",
            mensagem=_("downloads.preparando"),
        )
        sucesso = False

        try:
            sucesso = baixar_e_instalar(
                url, nome, pasta_jogo, referer,
                lambda b, t, p: self._progresso(identificador, b, t, p),
                lambda m: self._mensagem(identificador, m),
                cancelar,
                instalar,
            )
            dados = self.listar_tarefas().get(identificador, {})

            if cancelar.is_set():
                estado = "Cancelado"
                mensagem = _("downloads.cancelado_antes_inicio")
            elif sucesso:
                estado = "Concluído"
                mensagem = _("downloads.status_concluido", mensagem=nome)
            else:
                estado = "Falhou"
                mensagem = dados.get(
                    "mensagem",
                    _("downloads.erro", mensagem=_("instalacao.falha_operacao")),
                )

        except Exception as erro:
            estado, mensagem, sucesso = "Falhou", str(erro), False

        self._atualizar(
            identificador,
            estado=estado,
            sucesso=sucesso,
            mensagem=mensagem,
        )

        if self.on_concluido:
            try:
                self.on_concluido(identificador, sucesso, mensagem)
            except Exception:
                pass

        return sucesso

    def cancelar(self, identificador: str) -> bool:
        identificador = str(identificador)

        with self._lock:
            evento = self._cancelamentos.get(identificador)
            tarefa = self._tarefas.get(identificador)

            if not evento or not tarefa or tarefa["estado"] in self.ESTADOS_FINAIS:
                return False

            evento.set()
            futuro = self._futuros.get(identificador)

            if futuro and futuro.cancel():
                tarefa.update(
                    estado="Cancelado",
                    sucesso=False,
                    mensagem=_("downloads.cancelado_antes_inicio"),
                )

        self._mensagem(
            identificador, _("downloads.cancelamento_solicitado")
        )
        return True

    def cancelar_todos(self) -> None:
        with self._lock:
            ids = list(self._cancelamentos)

        for identificador in ids:
            self.cancelar(identificador)

    def encerrar(self, aguardar: bool = False) -> None:
        self.cancelar_todos()
        with self._lock:
            executor = self._executor

        executor.shutdown(wait=aguardar, cancel_futures=True)
