import random

def binary_sum_especial(A: str, B: str) -> str:
    soma = int(A, 2) + int(B, 2)
    if soma >= 2 ** 16:
        soma = (soma + 1) % (2 ** 16)
    return bin(soma)[2:].zfill(16)


def binary_sum(A: str, B: str) -> str:
    soma = (int(A, 2) + int(B, 2)) % (2 ** 16)
    return bin(soma)[2:].zfill(16)


def calc_checksum(data: str) -> str:
    """Calcula checksum de todo o segmento (em blocos de 16 bits)."""
    if len(data) % 16 != 0:
        data = data.ljust(((len(data) // 16) + 1) * 16, '0')

    result = '0' * 16
    for i in range(0, len(data), 16):
        bloco = data[i:i + 16]
        result = binary_sum_especial(result, bloco)
    return result


def segment_message(message: str, segSize: int) -> list[str]:
    """Transforma mensagem em binário e divide em blocos de segSize bits."""
    msgBin = ''.join([bin(ord(c))[2:].zfill(8) for c in message])
    segDatas = []
    for i in range(0, len(msgBin), segSize):
        segDatas.append(msgBin[i:i + segSize])
    return segDatas


def create_segments(segDatas: list[str], initNum: int = None) -> list[list[str]]:
    """Cria segmentos com número de sequência cumulativo e checksum final."""
    segments = []
    seqNum = initNum if initNum is not None else random.randint(0, 2**32 - 1)

    for data in segDatas:
        # --- 1ª linha: número de sequência (32 bits)
        seq_bin = bin(seqNum)[2:].zfill(32)

        # --- 2ª linha: número de reconhecimento (zerado)
        ack_bin = '0' * 32

        # --- 3ª linha (temporariamente checksum = 0)
        tamanho = bin(len(data) // 8)[2:].zfill(8)  # tamanho em bytes
        ack_bit = '0'
        zeros_finais = '0' * 7
        header_sem_checksum = '0' * 16 + tamanho + ack_bit + zeros_finais

        # --- Linhas de dados
        data_lines = [data[i:i + 32].ljust(32, '0') for i in range(0, len(data), 32)]

        # --- Junta tudo
        segment = [seq_bin, ack_bin, header_sem_checksum] + data_lines[:4]

        # --- Calcular checksum após montar o segmento completo
        all_bits = ''.join(segment)
        checksum = calc_checksum(all_bits)

        # --- Substituir checksum no cabeçalho
        header_completo = checksum + tamanho + ack_bit + zeros_finais
        segment[2] = header_completo

        # --- Armazenar o segmento final
        segments.append(segment)

        # --- Atualizar número de sequência para o próximo segmento
        seqNum += len(all_bits)

    return segments

def seg_message(message:list) -> list:
    data_segs = segment_message(message,128)

    return create_segments(data_segs)



def decode_segments(segments: list[list[str]]) -> str:
    """Reconstrói a string original a partir dos segmentos binários."""
    data_bits = ""

    for segment in segments:
        # Linhas de dados começam na linha 4 (índice 3)
        for linha in segment[3:]:
            data_bits += linha

    # Remove bits extras de padding (múltiplos de 8)
    if len(data_bits) % 8 != 0:
        data_bits = data_bits[:len(data_bits) - (len(data_bits) % 8)]

    # Converte blocos de 8 bits em caracteres
    mensagem = ""
    for i in range(0, len(data_bits), 8):
        byte = data_bits[i:i + 8]
        char = chr(int(byte, 2))
        mensagem += char

    return mensagem
