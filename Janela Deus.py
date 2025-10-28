import socket, time, random

IP = '127.0.0.1'
PORTA = 55555
JANELA = 5 
TEMPO = 1.0 
TAM_PAYLOAD_BITS = 128
TAM_PAYLOAD_BYTES = TAM_PAYLOAD_BITS // 8 # Tamanho MÁXIMO do payload em bytes

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
#Classe Envio Modificada
class Envio:
    def __init__(self, ip, porta):
        self.dest = (ip, porta) # Destino
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', 0)) 
        # Configura o socket para ser não-bloqueante
        self.sock.setblocking(False)
        print(f"Remetente (Envio) ouvindo em: {self.sock.getsockname()}")
        #Controle da janela deslizante 
        self.base = 0 
        self.prox_seq_num = 0 
        self.buffer_segmentos = {} 
        self.tempos_envio = {}
        self.acks_confirmados = set() 
        self.buffer_envio = [] 
        self.ultimo_seq_necessario = -1 

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

    def _processar_ack_recebido(self, ack_num_recebido):
        """Processa um ACK, marca como confirmado e desliza a janela."""
        if ack_num_recebido in self.acks_confirmados or ack_num_recebido < self.base: 
            return False 
        self.acks_confirmados.add(ack_num_recebido) 
        self.tempos_envio.pop(ack_num_recebido, None)
        print(f"[ACK] Recebido para segmento {ack_num_recebido}") 
#Deslizar a Janela
        while self.base in self.acks_confirmados: 
            dados_segmento = self.buffer_segmentos.pop(self.base, None) 
            if dados_segmento is None:
                break
            
            _, tamanho_segmento_bits = dados_segmento
            
            self.acks_confirmados.remove(self.base) 
            self.base += tamanho_segmento_bits
            print(f"Janela deslizou, nova base (em bits): {self.base}")
        return True
    
    def _tentar_receber_ack(self):
        try:
            msg_bytes, _ = self.sock.recvfrom(2048) 
            info = self._ler_segmento(msg_bytes) 
            if info and info['flag'] == 1: 
                mudou_janela = self._processar_ack_recebido(info['ack'])
                return mudou_janela
        except BlockingIOError:
            pass 
        except Exception as e:
            print(f"Erro ao tentar receber ACK: {e}")
        return False 
    
    def _verificar_timeouts(self):
        """Verifica se algum segmento enviado excedeu o tempo limite."""
        agora = time.time()
        timeouts_ocorridos = []
        for seq, envio_timestamp in list(self.tempos_envio.items()):
            if agora - envio_timestamp > TEMPO:
                timeouts_ocorridos.append(seq) 
        for seq in timeouts_ocorridos:
            if seq not in self.acks_confirmados and seq in self.buffer_segmentos:
                print(f"[TIMEOUT] Reenviando segmento {seq}") 
                segmento_bytes, _ = self.buffer_segmentos[seq]
                try:
                    self.sock.sendto(segmento_bytes, self.dest) 
                    self.tempos_envio[seq] = time.time()
                except Exception as e:
                    print(f"Erro ao reenviar segmento {seq} no timeout: {e}")


    def _enviar_novos_segmentos(self):
        while (len(self.buffer_segmentos) < JANELA) and self.buffer_envio: 
            seq, payload_bytes, tamanho_segmento_bits = self.buffer_envio.pop(0) 
            segmento_bytes = self._montar_segmento(seq, 0, 0, payload_bytes) 
            self.buffer_segmentos[seq] = (segmento_bytes, tamanho_segmento_bits)
            try:
                self.sock.sendto(segmento_bytes, self.dest) 
                print(f"[ENVIO] Segmento {seq} enviado pela primeira vez") 
                self.tempos_envio[seq] = time.time()
            except Exception as e:
                print(f"Erro ao enviar segmento {seq}: {e}")
                self.buffer_segmentos.pop(seq, None) 
                self.buffer_envio.insert(0, (seq, payload_bytes, tamanho_segmento_bits)) 
                break 
    
    def enfileirar_mensagens(self, lista_mensagens: list): 
        self.ultimo_seq_necessario = self.prox_seq_num -1 
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
                
                self.buffer_envio.append((seq, payload, tamanho_segmento_bits)) 
                
                print(f"[FILA] Segmento {seq} preparado ({len(payload)}B, {tamanho_segmento_bits} bits)") 
                
                self.prox_seq_num += tamanho_segmento_bits
                
                self.ultimo_seq_necessario = seq 
                idx += TAM_PAYLOAD_BYTES 
        self._enviar_novos_segmentos() 
    
    def esperar_confirmacao_total(self): 
        print(f"Aguardando confirmação até o segmento {self.ultimo_seq_necessario}...") 
        while self.base <= self.ultimo_seq_necessario: 
            janela_deslizou = self._tentar_receber_ack()
            self._enviar_novos_segmentos()
            self._verificar_timeouts()
            time.sleep(0.01)
            
        while len(self.buffer_segmentos) > 0:
            self._tentar_receber_ack()
            self._verificar_timeouts()
            time.sleep(0.01)
            
        print("[FIM] Todos os segmentos enfileirados foram confirmados.") #
#Encerrar 
    def fechar(self): 
        print("Fechando o remetente...") 
        try:
             self.sock.close() 
        except Exception as e:
            print(f"Erro ao fechar socket: {e}") 
        print("[FECHADO]")