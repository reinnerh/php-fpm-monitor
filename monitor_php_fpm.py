#!/usr/bin/env python3
import boto3, sys, logging, os, time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

asg = boto3.client('autoscaling', region_name='sa-east-1')
ssm = boto3.client('ssm', region_name='sa-east-1')

ASG_NAME = 'TESTER-IBAC'

def monitor_php_fpm(instance_id=None):
    """
    Monitora especificamente o PHP-FPM e suas configurações
    """
    try:
        if instance_id:
            instances = [instance_id]
        else:
            response = asg.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG_NAME])
            instances = [inst['InstanceId'] for inst in response['AutoScalingGroups'][0]['Instances'] 
                        if inst['LifecycleState'] == 'InService']
        
        if not instances:
            logging.warning("Nenhuma instância encontrada")
            return
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        local_dir = f"php_fpm_monitor_{timestamp}"
        os.makedirs(local_dir, exist_ok=True)
        
        for inst_id in instances:
            logging.info(f"Monitorando PHP-FPM de {inst_id}...")
            
            command = f"""
            echo "=== MONITORAMENTO PHP-FPM - {inst_id} ==="
            echo "Data/Hora: $(date)"
            echo "Uptime: $(uptime)"
            echo ""
            
            echo "=== STATUS DO PHP-FPM ==="
            systemctl status php*-fpm --no-pager -l 2>/dev/null || echo "PHP-FPM não encontrado"
            echo ""
            
            echo "=== CONFIGURAÇÕES DO POOL WWW ==="
            echo "Arquivo de configuração:"
            find /etc -name "www.conf" -path "*/php*/fpm/pool.d/*" 2>/dev/null | head -1
            echo ""
            echo "Configurações principais:"
            grep -E "^(pm|pm.max_children|pm.start_servers|pm.min_spare_servers|pm.max_spare_servers|pm.max_requests)" /etc/php*/fpm/pool.d/www.conf 2>/dev/null || echo "Configurações não encontradas"
            echo ""
            
            echo "=== PROCESSOS PHP-FPM ATUAIS ==="
            echo "Processo Master:"
            ps aux | grep "php-fpm: master" | grep -v grep || echo "Master não encontrado"
            echo ""
            echo "Total de processos worker:"
            WORKER_COUNT=\$(ps aux | grep "php-fpm: pool www" | grep -v grep | wc -l)
            echo "Workers ativos: \$WORKER_COUNT"
            echo ""
            echo "Processos por status:"
            ps aux | grep "php-fpm: pool www" | grep -v grep | head -10
            echo ""
            
            echo "=== ANÁLISE DE CONFIGURAÇÃO vs USO ==="
            MAX_CHILDREN=\$(grep "^pm.max_children" /etc/php*/fpm/pool.d/www.conf 2>/dev/null | cut -d'=' -f2 | tr -d ' ' || echo "N/A")
            echo "Configurado para máximo: \$MAX_CHILDREN processos"
            echo "Usando atualmente: \$WORKER_COUNT processos"
            
            if [ "\$MAX_CHILDREN" != "N/A" ]; then
                echo "Análise de uso:"
                if [ "\$WORKER_COUNT" -gt 0 ] && [ "\$MAX_CHILDREN" -gt 0 ] 2>/dev/null; then
                    if [ "\$WORKER_COUNT" -gt "\$((MAX_CHILDREN * 9 / 10))" ] 2>/dev/null; then
                        echo "🔴 CRÍTICO: Usando mais de 90% da capacidade!"
                    elif [ "\$WORKER_COUNT" -gt "\$((MAX_CHILDREN * 7 / 10))" ] 2>/dev/null; then
                        echo "⚠️  ATENÇÃO: Usando mais de 70% da capacidade"
                    else
                        echo "✅ Uso dentro do normal"
                    fi
                fi
            fi
            echo ""
            
            echo "=== USO DE MEMÓRIA ==="
            echo "Memória por processo PHP-FPM:"
            ps aux | grep "php-fpm: pool www" | grep -v grep | awk '{{sum+=\$6; count++}} END {{if(count>0) printf "Média: %.1f MB por processo\\nTotal: %.1f MB\\nProcessos: %d\\n", sum/count/1024, sum/1024, count}}'
            echo ""
            
            echo "=== LOGS DE ERRO PHP-FPM ==="
            echo "Últimos 10 erros:"
            tail -10 /var/log/php*-fpm.log 2>/dev/null || echo "Log não encontrado"
            echo ""
            echo "Erros de sobrecarga (max_children):"
            grep -c "server reached.*max_children" /var/log/php*-fpm.log 2>/dev/null || echo "0"
            echo ""
            echo "Erros de pool busy:"
            grep -c "pool.*seems busy" /var/log/php*-fpm.log 2>/dev/null || echo "0"
            echo ""
            
            echo "=== CONEXÕES ATIVAS ==="
            echo "Conexões na porta 9000 (PHP-FPM):"
            netstat -tulpn 2>/dev/null | grep :9000 || ss -tulpn 2>/dev/null | grep :9000 || echo "Nenhuma conexão na porta 9000"
            echo ""
            
            echo "=== RESUMO ==="
            if pgrep php-fpm > /dev/null; then
                echo "✅ PHP-FPM está rodando"
            else
                echo "❌ PHP-FPM não está rodando"
            fi
            
            echo "=== FIM DO MONITORAMENTO ==="
            """
            
            try:
                response = ssm.send_command(
                    InstanceIds=[inst_id],
                    DocumentName='AWS-RunShellScript',
                    Parameters={'commands': [command]},
                    TimeoutSeconds=120
                )
                
                command_id = response['Command']['CommandId']
                
                # Aguarda execução
                for _ in range(30):
                    time.sleep(2)
                    result = ssm.get_command_invocation(CommandId=command_id, InstanceId=inst_id)
                    
                    if result['Status'] in ['Success', 'Failed']:
                        break
                
                if result['Status'] == 'Success':
                    report_file = f"{local_dir}/php_fpm_{inst_id}_{timestamp}.txt"
                    with open(report_file, 'w') as f:
                        f.write(result['StandardOutputContent'])
                    
                    logging.info(f"✅ Monitoramento PHP-FPM de {inst_id} salvo em: {report_file}")
                    
                    # Mostra resumo no terminal
                    print(f"\n=== RESUMO RÁPIDO - {inst_id} ===")
                    lines = result['StandardOutputContent'].split('\n')
                    for line in lines:
                        if any(keyword in line for keyword in ['Usando atualmente:', 'Percentual de uso:', '🔴', '⚠️', '✅']):
                            print(line)
                    
                else:
                    logging.error(f"❌ Erro ao monitorar {inst_id}: {result.get('StandardErrorContent', 'Erro desconhecido')}")
                    
            except Exception as e:
                logging.error(f"❌ Erro ao processar {inst_id}: {e}")
        
        logging.info(f"🎯 Relatórios salvos em: ./{local_dir}/")
        
    except Exception as e:
        logging.error(f"Erro geral: {e}")

if __name__ == "__main__":
    instance_id = None
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("Uso:")
            print("  python3 monitor_php_fpm.py                    # Monitora todas as instâncias")
            print("  python3 monitor_php_fpm.py i-1234567890abcdef0  # Monitora instância específica")
            print("")
            print("Este script monitora especificamente:")
            print("  - Configurações do PHP-FPM (pm.max_children, etc.)")
            print("  - Uso atual vs configuração máxima")
            print("  - Processos ativos e uso de memória")
            print("  - Erros de sobrecarga nos logs")
            print("  - Status geral do serviço")
            sys.exit(0)
        else:
            instance_id = sys.argv[1]
    
    monitor_php_fpm(instance_id)
