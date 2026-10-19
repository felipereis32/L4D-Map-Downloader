import os
import winreg
from pathlib import Path
import vdf

class SteamGameDetector:
    APP_ID = "500"
    EXECUTAVEL = "left4dead.exe"

    def __init__(self):
        self.steam_path = self._find_steam_path()

    def _find_steam_path(self):
        registry_keys = [
            (
                winreg.HKEY_CURRENT_USER,
                r"Software\Valve\Steam",
            ),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Valve\Steam",
            ),
        ]

        for hive, key_path in registry_keys:
            try:
                with winreg.OpenKey(hive, key_path) as key:
                    path, _ = winreg.QueryValueEx(key, "SteamPath")
                    path = Path(os.path.expandvars(path)).expanduser()

                    if path.is_dir():
                        return path

            except OSError:
                continue

        return None

    def localizar_jogo(self, app_id="500"):
        if self.steam_path is None:
            return None

        arquivo_bibliotecas = (
            self.steam_path / "steamapps" / "libraryfolders.vdf"
        )

        if not arquivo_bibliotecas.is_file():
            return None

        try:
            with arquivo_bibliotecas.open(
                "r", encoding="utf-8-sig"
            ) as arquivo:
                dados = vdf.load(arquivo)
        except (OSError, ValueError):
            return None

        bibliotecas = dados.get("libraryfolders", {})
        caminhos = [self.steam_path]

        for biblioteca in bibliotecas.values():
            if isinstance(biblioteca, dict):
                caminho = biblioteca.get("path")
            else:
                caminho = biblioteca

            if caminho:
                caminhos.append(Path(caminho))

        bibliotecas_unicas = list(dict.fromkeys(caminhos))

        for biblioteca in bibliotecas_unicas:
            manifesto = (
                biblioteca
                / "steamapps"
                / f"appmanifest_{app_id}.acf"
            )

            if not manifesto.is_file():
                continue

            try:
                with manifesto.open(
                    "r", encoding="utf-8-sig"
                ) as arquivo:
                    dados_jogo = vdf.load(arquivo)

                estado = dados_jogo.get("AppState", {})
                installdir = estado.get("installdir")

                if not installdir:
                    continue

                pasta_jogo = (
                    biblioteca
                    / "steamapps"
                    / "common"
                    / installdir
                )

                if (pasta_jogo / self.EXECUTAVEL).is_file():
                    return pasta_jogo

            except (OSError, ValueError):
                continue

        return None

    def validar_pasta_manual(self, caminho):
        """
        Recebe a pasta que contém left4dead.exe.
        Retorna o caminho validado ou None.
        """
        try:
            pasta = Path(caminho.strip().strip('"')).expanduser()
            pasta = pasta.resolve()

            if not pasta.is_dir():
                return None

            executavel = pasta / self.EXECUTAVEL

            if executavel.is_file():
                return pasta

        except (OSError, ValueError, RuntimeError):
            return None

        return None

    def jogo_instalado(self, app_id="500"):
        return self.localizar_jogo(app_id) is not None
