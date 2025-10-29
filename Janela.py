import socket, time, random
import threading # <<< ADICIONADO

IP = '127.0.0.1'
PORTA = 55555
JANELA = 5
TEMPO = 1.0 # Timeout individual em segundos (era TEMPO)
TAM_PAYLOAD_BITS = 128
TAM_PAYLOAD_BYTES = TAM_PAYLOAD_BITS // 8 # Tamanho MÁXIMO do payload em bytes

# (Funções de Checksum e Conversão - Sem Mudanças)
# Funções de Checksum
def binary_sum_especial(A: str, B: str) -> str:
    soma = int(A, 2) + int(B, 2)
    if soma >= 2 ** 16:
        soma = (soma + 1) % (2 ** 16)
    return bin(soma)[2:].zfill(16)

def calc_checksum(data: str) -> str:
    if len(data) % 16 != 0:
        data = data.ljust(((len(data) // 16) + 1) * 16, '0')
    result = '0' * 16
    for i in range(0, len(data), 16):
        bloco = data[i:i + 16]
        result = binary_sum_especial(result, bloco)
    return result

def verify_checksum(segment_str: str) -> bool:
    if len(segment_str) < 96:
        return False
    checksum_recebido = segment_str[64:80]
    header1 = segment_str[0:32]
    header2 = segment_str[32:64]
    header3_sem_checksum = '0' * 16 + segment_str[80:96]
    payload = segment_str[96:]
    string_para_verificar = header1 + header2 + header3_sem_checksum + payload
    checksum_calculado = calc_checksum(string_para_verificar)
    checksum_ok = (checksum_calculado == checksum_recebido)
    return checksum_ok

# Conversão Binário <-> Bytes
def string_binaria_para_bytes(s_bin: str) -> bytes:
    if len(s_bin) % 8 != 0:
        s_bin = s_bin.ljust((len(s_bin) + 7) // 8 * 8, '0')
    b_array = bytearray()
    for i in range(0, len(s_bin), 8):
        byte_str = s_bin[i:i+8]
        try:
            b_array.append(int(byte_str, 2))
        except ValueError:
            return b''
    return bytes(b_array)

def bytes_para_string_binaria(b: bytes) -> str:
    return ''.join([bin(byte)[2:].zfill(8) for byte in b])

#Classe Envio Modificada para Multi-Thread
class Envio:
    def __init__(self, ip, porta):
        self.dest = (ip, porta) # Destino
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', 0))
        # <<< MODIFICADO: Timeout no socket para a thread de ACK não bloquear indefinidamente
        self.sock.settimeout(0.5)
        # self.sock.setblocking(False) # Não é mais necessário com timeout e thread separada
        print(f"Remetente (Envio) ouvindo em: {self.sock.getsockname()}")

        #Controle da janela deslizante
        self.base = 0
        self.prox_seq_num = 0
        # Buffer armazena {seq_bits: (segmento_bytes, tamanho_segmento_bits)}
        self.buffer_segmentos = {}
        # <<< MODIFICADO: Armazena {seq_bits: threading.Timer object}
        self.tempos_envio = {}
        self.acks_confirmados = set()
        self.buffer_envio = [] # Fila da aplicação [(seq, payload, tamanho_bits)]
        self.ultimo_seq_necessario = -1
        self.seq_nums_gerados = set() # Guarda todos os seq nums gerados

        # <<< ADICIONADO: Lock para segurança de thread >>>
        self.lock = threading.Lock()
        self.rodando = True # Flag para controlar a thread de ACK

        # <<< ADICIONADO: Inicia a thread de recebimento de ACKs >>>
        self.th_ack = threading.Thread(target=self._receber_acks, daemon=True)
        self.th_ack.start()


    # (Funções _montar_segmento e _ler_segmento - Sem Mudanças Funcionais)
    #Montar e Ler Segmentos
    def _montar_segmento(self, seq: int, ack_num: int, ack_flag: int, dados_payload: bytes) -> bytes:
        dados_bin = bytes_para_string_binaria(dados_payload)
        dados_bin = dados_bin.ljust(((len(dados_bin) + 15) // 16) * 16, '0')
        seq_bin = bin(seq & 0xFFFFFFFF)[2:].zfill(32)
        ack_bin = bin(ack_num & 0xFFFFFFFF)[2:].zfill(32)
        tamanho_bytes = len(dados_payload)
        tamanho_bin = bin(tamanho_bytes & 0xFF)[2:].zfill(8)
        ack_bit_bin = '1' if ack_flag == 1 else '0'
        zeros_finais = '0' * 7
        header_sem_checksum = '0' * 16 + tamanho_bin + ack_bit_bin + zeros_finais
        segmento_str_temp = seq_bin + ack_bin + header_sem_checksum + dados_bin
        checksum_bin = calc_checksum(segmento_str_temp)
        header_final = checksum_bin + tamanho_bin + ack_bit_bin + zeros_finais
        segmento_final_str = seq_bin + ack_bin + header_final + dados_bin
        segmento_bytes = string_binaria_para_bytes(segmento_final_str)
        return segmento_bytes

    def _ler_segmento(self, msg_bytes: bytes):
        msg_bin = bytes_para_string_binaria(msg_bytes)
        if len(msg_bin) < 96:
            return None
        if not verify_checksum(msg_bin):
            print("[ACK RECV] Checksum inválido no ACK.") # Debug
            return None
        seq_bin = msg_bin[0:32]
        ack_bin = msg_bin[32:64]
        header3_bin = msg_bin[64:96]
        dados_bin = msg_bin[96:]
        tamanho_bin = header3_bin[16:24]
        ack_bit_bin = header3_bin[24:25]
        seq_int = int(seq_bin, 2)
        ack_int = int(ack_bin, 2)
        flag_int = int(ack_bit_bin, 2)
        tamanho_int = int(tamanho_bin, 2)
        dados_bytes_com_padding = string_binaria_para_bytes(dados_bin)
        dados_payload_originais = dados_bytes_com_padding[:tamanho_int]
        return {'seq': seq_int, 'ack': ack_int, 'flag': flag_int, 'dados': dados_payload_originais}

    # <<< NOVA FUNÇÃO: Thread para receber ACKs >>>
    def _receber_acks(self):
        """Função executada pela thread dedicada ao recebimento de ACKs."""
        while self.rodando:
            try:
                msg_bytes, _ = self.sock.recvfrom(2048) # Espera por dados (com timeout)
                info = self._ler_segmento(msg_bytes)
                if info and info['flag'] == 1: # Se for um ACK válido
                    with self.lock: # <<< Protege acesso às variáveis compartilhadas
                        mudou_janela = self._processar_ack_recebido(info['ack'])
                        if mudou_janela:
                            # Tenta enviar mais segmentos se a janela deslizou
                            self._enviar_novos_segmentos()
            except socket.timeout:
                continue # Timeout é normal, apenas tenta receber de novo
            except OSError:
                if self.rodando: # Se o socket foi fechado, encerra a thread
                    print("[ACK Thread] Socket fechado.")
                break
            except Exception as e:
                if self.rodando:
                    print(f"[ACK Thread] Erro inesperado: {e}")

    # <<< NOVAS FUNÇÕES: Controle de Timers Individuais >>>
    def _iniciar_timer(self, seq):
        """Inicia um timer individual para o segmento 'seq'."""
        self._parar_timer(seq) # Garante que não haja timer antigo rodando para o mesmo seq
        # Cria um timer que chamará _tratar_timeout(seq) após TEMPO segundos
        timer = threading.Timer(TEMPO, self._tratar_timeout, args=(seq,))
        self.tempos_envio[seq] = timer # Armazena o objeto Timer
        timer.start()

    def _parar_timer(self, seq):
        """Para e remove o timer associado ao segmento 'seq'."""
        timer = self.tempos_envio.pop(seq, None) # Remove o timer do dicionário
        if timer:
            timer.cancel() # Cancela a execução do timer se ele ainda não disparou

    # <<< MODIFICADO: Função chamada pelo Timer quando ocorre Timeout >>>
    def _tratar_timeout(self, seq):
        """Função chamada por um objeto threading.Timer quando o tempo expira."""
        with self.lock: # <<< Protege acesso
            # Se o segmento já foi confirmado enquanto o timer estava 'voando', ignora
            if seq in self.acks_confirmados:
                return
            # Se o segmento não está mais no buffer (foi confirmado e base deslizou), ignora
            if seq not in self.buffer_segmentos:
                return

            print(f"[TIMEOUT] Reenviando segmento {seq}")
            segmento_bytes, _ = self.buffer_segmentos[seq] # Pega os bytes para reenviar
            try:
                self.sock.sendto(segmento_bytes, self.dest)
                self._iniciar_timer(seq) # Reinicia o timer para este segmento
            except Exception as e:
                print(f"Erro ao reenviar segmento {seq} no timeout: {e}")
                # Não remove do buffer, tentará reenviar no próximo ciclo ou timeout

    # (Função _processar_ack_recebido - Sem Mudanças Funcionais, mas agora chamada pela thread de ACK)
    def _processar_ack_recebido(self, ack_num_recebido):
        """Processa um ACK, marca como confirmado e desliza a janela."""
        # Acesso a self.acks_confirmados, self.tempos_envio, self.base, self.buffer_segmentos
        # PRECISA ser chamado dentro de 'with self.lock:'
        if ack_num_recebido in self.acks_confirmados or ack_num_recebido < self.base:
            return False
        self.acks_confirmados.add(ack_num_recebido)
        self._parar_timer(ack_num_recebido) # <<< MODIFICADO: Chama _parar_timer
        print(f"[ACK] Recebido para segmento {ack_num_recebido}")
        #Deslizar a Janela
        mudou_base = False
        while self.base in self.acks_confirmados:
            dados_segmento = self.buffer_segmentos.pop(self.base, None)
            if dados_segmento is None:
                break
            _, tamanho_segmento_bits = dados_segmento
            self.acks_confirmados.remove(self.base) # Remove do set de ACKs pendentes
            # Note: Não precisamos mais remover de self.tempos_envio aqui, _parar_timer já fez
            self.base += tamanho_segmento_bits
            print(f"Janela deslizou, nova base (em bits): {self.base}")
            mudou_base = True
        return mudou_base # Retorna True se a base deslizou

    # (Função _tentar_receber_ack foi removida, a lógica está em _receber_acks)
    # (Função _verificar_timeouts foi removida, a lógica está em _tratar_timeout)

    # <<< MODIFICADO: Função de Envio >>>
    def _enviar_novos_segmentos(self):
        """Envia novos segmentos da fila buffer_envio se a janela permitir."""
        # Acesso a self.buffer_envio, self.buffer_segmentos, self.tempos_envio
        # PRECISA ser chamado dentro de 'with self.lock:'
        # Envia enquanto houver pacotes "não enviados" ou "não confirmados"
        # E o número de pacotes "em voo" (com timer ativo) for menor que JANELA
        while (len(self.tempos_envio) < JANELA) and self.buffer_envio:
            seq, payload_bytes, tamanho_segmento_bits = self.buffer_envio[0] # Pega sem remover ainda

            # Se este segmento já está no buffer (foi preparado mas ainda não enviado/confirmado)
            # E ainda não tem um timer (significa que não foi enviado ainda)
            if seq not in self.tempos_envio:
                self.buffer_envio.pop(0) # Remove da fila de espera
                segmento_bytes = self._montar_segmento(seq, 0, 0, payload_bytes)
                self.buffer_segmentos[seq] = (segmento_bytes, tamanho_segmento_bits) # Guarda para retransmitir
                try:
                    self.sock.sendto(segmento_bytes, self.dest)
                    print(f"[ENVIO] Segmento {seq} enviado pela primeira vez")
                    self._iniciar_timer(seq) # <<< MODIFICADO: Inicia timer individual
                except Exception as e:
                    print(f"Erro ao enviar segmento {seq}: {e}")
                    # Devolve para o início da fila se falhar o envio
                    self.buffer_envio.insert(0, (seq, payload_bytes, tamanho_segmento_bits))
                    self.buffer_segmentos.pop(seq, None) # Remove do buffer de retransmissão
                    break # Para de tentar enviar por ora
            else:
                 # Se o primeiro da fila já foi enviado (tem timer),
                 # não há novos segmentos para enviar no momento
                 break

    # <<< MODIFICADO: Função para Enfileirar Mensagens >>>
    def enfileirar_mensagens(self, lista_mensagens: list):
        """Coloca mensagens na fila de envio, dividindo e aplicando numeração."""
        with self.lock: # <<< Protege acesso
            if isinstance(lista_mensagens, str):
                lista_mensagens = [lista_mensagens]

            novos_seqs = [] # Guarda os seq nums gerados nesta chamada
            for mensagem in lista_mensagens:
                mensagem_bytes = mensagem.encode('utf-8') if isinstance(mensagem, str) else mensagem
                idx = 0
                while idx < len(mensagem_bytes):
                    payload = mensagem_bytes[idx : idx + TAM_PAYLOAD_BYTES]
                    if not payload:
                        break

                    seq = self.prox_seq_num
                    dados_bin = bytes_para_string_binaria(payload)
                    dados_bin_len_padded = ((len(dados_bin) + 15) // 16) * 16
                    tamanho_segmento_bits = 96 + dados_bin_len_padded

                    # Adiciona na fila de espera para envio
                    self.buffer_envio.append((seq, payload, tamanho_segmento_bits))
                    self.seq_nums_gerados.add(seq) # Guarda o seq num gerado
                    novos_seqs.append(seq)

                    print(f"[FILA] Segmento {seq} preparado ({len(payload)}B, {tamanho_segmento_bits} bits)")

                    self.prox_seq_num += tamanho_segmento_bits
                    self.ultimo_seq_necessario = seq
                    idx += TAM_PAYLOAD_BYTES

            # Tenta enviar imediatamente o que couber na janela
            self._enviar_novos_segmentos()
        return novos_seqs # Retorna os seq nums gerados

    # <<< MODIFICADO: Função para Esperar Confirmação >>>
    def esperar_confirmacao_total(self):
        """Espera (bloqueia) até que todos os segmentos enfileirados sejam confirmados."""
        print(f"Aguardando confirmação para todos os segmentos...")

        # Espera enquanto o conjunto de todos os seq nums gerados
        # não for um subconjunto dos acks confirmados.
        while True:
            with self.lock: # <<< Protege acesso
                if self.seq_nums_gerados.issubset(self.acks_confirmados):
                    break # Todos foram confirmados
            time.sleep(0.1) # Pausa para não consumir CPU excessivamente

        print("[FIM] Todos os segmentos enfileirados foram confirmados.") #

    # <<< MODIFICADO: Função para Encerrar >>>
    def fechar(self):
        """Encerra a thread de ACK, fecha o socket e cancela timers."""
        print("Fechando o remetente...")
        self.rodando = False # Sinaliza para a thread de ACK parar
        if self.th_ack.is_alive():
             self.th_ack.join(timeout=1.0) # Espera a thread de ACK terminar (com timeout)
        self.sock.close()
        with self.lock: # Cancela todos os timers restantes
            for seq in list(self.tempos_envio.keys()):
                self._parar_timer(seq)
        print("[FECHADO]")
