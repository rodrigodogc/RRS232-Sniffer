# RS-232 Sniffer

Sniffer serial RS-232 para engenharia reversa de protocolos fechados. Captura em tempo real os fluxos **RX** e **TX** de um equipamento (cada um grampeado em um adaptador USB-RS232 diferente, ambos usados apenas em modo leitura), exibe os pacotes lado a lado com timestamp de alta resolução, oferece parsing rápido (hex/ASCII, framing configurável, checksum/CRC) e grava tudo em SQLite para análise posterior.

## Funcionalidades

- **Captura passiva de duas portas simultâneas** (RX e TX em portas COM independentes), cada uma em sua própria thread, sem nunca escrever no barramento.
- **Duas visualizações ao vivo**, alternáveis: colunas separadas (RX | TX) ou timeline única intercalada por cor.
- **Framing configurável** (Strategy pattern), aplicável ao vivo ou sobre sessões já gravadas:
  - Sem framing (bruto) — cada chunk lido vira uma linha.
  - Delimitador (STX/ETX), com suporte opcional a **byte-stuffing** (escape) para protocolos que protegem o payload contra colisão com os próprios delimitadores.
  - Timeout entre bytes (agrupa por silêncio na linha).
  - Tamanho fixo.
- **Checksum/CRC automático** (XOR, SUM8/16, CRC8, CRC16-CCITT, CRC16-MODBUS) com verificação do último byte do pacote — útil para descobrir se o fabricante usa um checksum simples.
- **Filtro/busca por sequência de bytes** com destaque em tempo real.
- **Armazenamento em SQLite**: bytes brutos e pacotes derivados ficam em tabelas separadas, então mudar a configuração de framing depois não reprocessa nem perde o dado original.
- **Revisão de sessões salvas**: reabra qualquer captura antiga e teste configurações de framing diferentes sem precisar do hardware conectado.
- **Exportação** para CSV ou hexdump em texto, pela UI ou via CLI.

## Instalação

Requer Python 3.10+.

```bash
pip install -r requirements.txt
```

Para rodar os testes, instale também:

```bash
pip install -r requirements-dev.txt
```

## Uso

### Interface gráfica

```bash
python main.py
```

Na barra superior, selecione a porta COM e baud rate de cada linha (RX e TX), dê um nome à sessão e clique em **Iniciar captura**. Os pacotes aparecem em tempo real; use **Configurar framing** para agrupar os bytes brutos como pacotes e **Sessões salvas** para revisar capturas anteriores ou exportá-las.

### Simulador de tráfego (`testes.py`)

Sem o hardware do fabricante disponível, use o simulador para gerar tráfego binário realista (posição X/Y, ângulo, offset, heartbeat) em uma porta COM e validar o sniffer na outra ponta:

```bash
python testes.py --port COM4 --baud 9600 --interval 0.2
python testes.py --stuffing              # simula um protocolo com byte-stuffing (escape 0x1B)
```

Veja `python testes.py --help` para todas as opções.

### Exportação via linha de comando

```bash
python -m serial_sniffer.scripts.export_cli list
python -m serial_sniffer.scripts.export_cli export <session_id> --format csv
```

### Testes

```bash
pytest
```

## Arquitetura

```
serial_sniffer/
  capture/    threads de leitura serial (SerialPortReader) e orquestração da sessão (CaptureSession)
  parsing/    estratégias de framing (Strategy pattern), checksum, formatação hex/ASCII, filtro
  storage/    schema e acesso ao SQLite (raw_chunks imutável + packets derivados por config de framing)
  models/     dataclasses e enums compartilhados (Session, Packet, FrameConfigDTO...)
  ui/         interface CustomTkinter (barra superior, views, diálogos, revisão de sessões)
  scripts/    CLI de exportação
  tests/      testes unitários (pytest)
```

**Princípio central de storage:** os bytes brutos gravados no banco nunca dependem de framing — framing é uma lente de análise aplicada em memória, ao vivo ou sobre uma sessão histórica, e persistida apenas como cache derivado. Isso permite testar diferentes hipóteses de framing sobre a mesma captura sem perder o dado original.

## Dados locais

A pasta `data/` (banco SQLite, logs, exportações) é gerada automaticamente na primeira execução e fica fora do controle de versão (veja `.gitignore`) — é estado local da máquina, não código-fonte.
