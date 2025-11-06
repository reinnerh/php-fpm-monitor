# Monitor PHP-FPM com SSM e Auto Scaling

Script Python que monitora configurações PHP-FPM, detecta gargalos e sugere otimizações via SSM.

## 🚀 Funcionalidades

- **Monitoramento Automático**: Análise de pools PHP-FPM
- **Detecção de Gargalos**: Identifica problemas de performance
- **Integração SSM**: Execução remota via Systems Manager
- **Relatórios Detalhados**: Análise completa de configurações

## 🛠️ Tecnologias

- Python 3.8+
- AWS Systems Manager (SSM)
- Boto3 SDK
- Análise de logs PHP-FPM

## 📁 Arquivos

- `monitor_php_fpm.py` - Script principal de monitoramento
- `requirements.txt` - Dependências Python

## 🔧 Uso

```bash
python3 monitor_php_fpm.py
grep 'CRÍTICO' php_fpm_monitor_*/php_fpm_*.txt
aws ssm send-command --document-name 'AWS-RunShellScript' --targets 'Key=tag:Environment,Values=production'
```
