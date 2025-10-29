# transmissor_sr_bruto.py
# Implementação da janela deslizante (Selective Repeat)
# Manipulação "bruta" dos bits (sem struct)
# 32 bits sequência | 32 bits ack | 1 bit flag | resto reservado | dados

import socket
import threading
import time

IP_ROTEADOR = '127.0.0.1'
PORTA_ROTEADOR = 55555
JANELA = 5
TEMPO_ESPERA = 5.0
TAM_DADOS = 1024

def int_para_bytes(valor, n_bytes=4):
    """Converte inteiro em lista de bytes (big-endian) sem struct."""
    return bytes([(valor >> (8 * i)) & 0xFF for i in reversed(range(n_bytes))])

def bytes_para_int(b):
    """Converte bytes (big-endian) em inteiro."""
    val = 0
    for byte in b:
        val = (val << 8) | byte
    return val

def montar_seg(seq, ack, flag_ack, dados):
    """
    Monta o segmento manualmente:
    - 32 bits seq
    - 32 bits ack
    - 1 bit flag + 31 bits vazios
    """
    parte_seq = int_para_bytes(seq, 4)
    parte_ack = int_para_bytes(ack, 4)
    # Cria 32 bits de flag (somente 1 bit usado)
    bits_flag = (flag_ack & 1) << 31
    parte_flag = int_para_bytes(bits_flag, 4)
    cabecalho = parte_seq + parte_ack + parte_flag
    return cabecalho + (dados if dados else b'')

def ler_seg(seg):
    if len(seg) < 12:
        return None
    seq = bytes_para_int(seg[0:4])
    ack = bytes_para_int(seg[4:8])
    bits_flag = bytes_para_int(seg[8:12])
    flag_ack = (bits_flag >> 31) & 1
    dados = seg[12:]
    return {'seq': seq, 'ack': ack, 'flag': flag_ack, 'dados': dados}
# --------------------------- Classe principal ---------------------------
class EnviadorSR:
    def __init__(self, ip_roteador, porta_roteador):
        self.destino = (ip_roteador, porta_roteador)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', 0))
        self.sock.settimeout(0.5)

        self.base = 0
        self.prox_seq = 0
        self.segs = {}
        self.timers = {}
        self.confirmados = set()
        self.lock = threading.Lock()
        self.rodando = True

        self.th_ack = threading.Thread(target=self.receber_acks, daemon=True)
        self.th_ack.start()

    # ------------------------- Temporizadores -------------------------

    def iniciar_timer(self, seq):
        self.parar_timer(seq)
        t = threading.Timer(TEMPO_ESPERA, self.tratar_timeout, args=(seq,))
        self.timers[seq] = t
        t.start()

    def parar_timer(self, seq):
        t = self.timers.pop(seq, None)
        if t:
            try:
                t.cancel()
            except Exception:
                pass

    def tratar_timeout(self, seq):
        with self.lock:
            if seq in self.confirmados:
                return
            seg = self.segs.get(seq)
            if not seg:
                return
            print(f"[TEMPO ESGOTADO] Reenviando seq {seq}")
            self.sock.sendto(seg, self.destino)
            self.iniciar_timer(seq)

    # --------------------------- Receber ACK ---------------------------

    def receber_acks(self):
        while self.rodando:
            try:
                dados, _ = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            info = ler_seg(dados)
            if not info:
                continue
            if info['flag'] == 1:
                ack = info['ack']
                with self.lock:
                    if ack in self.confirmados:
                        continue
                    self.confirmados.add(ack)
                    self.parar_timer(ack)
                    print(f"[ACK] Recebido ACK para {ack}")

                    while self.base in self.confirmados:
                        del self.segs[self.base]
                        self.base += 1

                    self.enviar_pendentes()

    # --------------------------- Envio ---------------------------

    def enviar_pendentes(self):
        """Envia até 4 pacotes de uma vez (janela deslizante)."""
        for seq in range(self.base, self.base + JANELA):
            if seq not in self.segs:
                continue
            if seq in self.timers:
                continue
            seg = self.segs[seq]
            self.sock.sendto(seg, self.destino)
            print(f"[ENVIO] Segmento {seq} enviado")
            self.iniciar_timer(seq)

    def adicionar_dados(self, lista_dados):
        """Prepara pacotes e envia até o limite da janela."""
        with self.lock:
            for dado in lista_dados:
                if isinstance(dado, str):
                    dado = dado.encode('utf-8')
                seq = self.prox_seq
                seg = montar_seg(seq, 0, 0, dado)
                self.segs[seq] = seg
                print(f"[FILA] Seq {seq} preparado ({len(dado)} bytes)")
                self.prox_seq += 1
            self.enviar_pendentes()

    def enviar_e_esperar(self, lista_dados):
        """Modo bloqueante: envia tudo e espera todos ACKs."""
        self.adicionar_dados(lista_dados)
        inicio = self.base
        fim = self.prox_seq
        alvo = set(range(inicio, fim))
        while True:
            with self.lock:
                if alvo.issubset(self.confirmados):
                    break
            time.sleep(0.05)
        print("[CONCLUÍDO] Todos os segmentos foram reconhecidos.")

    # --------------------------- Encerrar ---------------------------

    def fechar(self):
        self.rodando = False
        self.sock.close()
        with self.lock:
            for seq in list(self.timers.keys()):
                self.parar_timer(seq)
        print("[ENVIADOR] Encerrado.")
