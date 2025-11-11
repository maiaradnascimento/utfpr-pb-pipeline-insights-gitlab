"""
CLI - Generate Recommendations

Gera recomendações usando Intelligent Strategy (IA Inteligente).
"""

import os
import sys
import argparse
import pandas as pd
from pathlib import Path

# Adiciona diretório raiz ao path para imports absolutos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.core.config import Config
from src.strategies import IntelligentStrategy


def main():
    """Gera recomendações usando Intelligent Strategy"""
    
    parser = argparse.ArgumentParser(description="Gera recomendações de otimização com IA")
    parser.add_argument(
        "--input",
        default=None,
        help="Arquivo CSV com pipelines (default: dados/processed/{PROJECT_ID}/pipelines.csv)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Arquivo de saída (default: dados/processed/{PROJECT_ID}/recomendacoes_ia_inteligente.csv)"
    )
    
    args = parser.parse_args()
    
    # Validar config
    Config.validate()
    
    # Determina caminhos usando Config
    input_file = args.input or (Config.DATA_PROCESSED_DIR / "pipelines.csv")
    output_file = args.output or (Config.DATA_PROCESSED_DIR / "recomendacoes_ia_inteligente.csv")
    
    # Carregar dados
    print(f"📊 Carregando dados: {input_file}")
    try:
        df = pd.read_csv(input_file)
        print(f"   ✅ {len(df)} pipelines carregados")
    except FileNotFoundError:
        print(f"   ❌ Arquivo não encontrado: {input_file}")
        print(f"   💡 Execute primeiro: python src/cli/fetch.py")
        return 1
    
    # Usa Intelligent Strategy
    strategy = IntelligentStrategy()
    print(f"\n🎨 Estratégia: Intelligent-AI")
    print(f"   Nome: {strategy.name}")
    
    # Gerar recomendações
    print(f"\n🔄 Gerando recomendações...")
    try:
        recommendations = strategy.recommend(df)
        print(f"   ✅ {len(recommendations)} recomendações geradas")
    except Exception as e:
        print(f"   ❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    if not recommendations:
        print(f"   ℹ️  Nenhuma recomendação gerada (dados normais)")
        return 0
    
    # Converter para DataFrame
    recs_dict = [rec.to_dict() for rec in recommendations]
    df_recs = pd.DataFrame(recs_dict)
    
    # Salvar
    print(f"\n💾 Salvando resultados...")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_recs.to_csv(output_file, index=False)
    print(f"   ✅ Salvo em: {output_file}")
    
    # Gerar relatório markdown
    md_file = output_file.with_suffix('.md')
    print(f"   📄 Gerando relatório: {md_file}")
    
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# Recomendações - {strategy.name}\n\n")
        f.write(f"**Gerado em**: {pd.Timestamp.now()}\n")
        f.write(f"**Pipelines analisados**: {len(df)}\n")
        f.write(f"**Recomendações**: {len(recommendations)}\n\n")
        f.write("---\n\n")
        
        for i, rec in enumerate(recommendations, 1):
            f.write(f"## {i}. Pipeline #{rec.pipeline_id}\n\n")
            f.write(f"**Categoria**: {rec.category}\n")
            f.write(f"**Ação**: {rec.action}\n")
            f.write(f"**Motivo**: {rec.reason}\n")
            f.write(f"**Ganho estimado**: {rec.estimated_gain_sec:.0f}s ({rec.estimated_gain_pct:.1f}%)\n")
            f.write(f"**Confiança**: {rec.confidence}\n\n")
            
            if rec.yaml_code:
                f.write("**Código YAML**:\n")
                f.write("```yaml\n")
                f.write(rec.yaml_code)
                f.write("\n```\n\n")
            
            f.write("---\n\n")
    
    print(f"   ✅ Relatório salvo em: {md_file}")
    
    # Resumo
    print(f"\n📊 RESUMO:")
    print(f"   Total: {len(recommendations)} recomendações")
    
    by_category = df_recs.groupby('category').size().to_dict()
    for cat, count in by_category.items():
        print(f"   - {cat}: {count}")
    
    total_gain = df_recs['estimated_gain_sec'].sum()
    print(f"\n   💰 Ganho total estimado: {total_gain:.0f}s ({total_gain/60:.1f} min)")
    
    print(f"\n🎉 Concluído!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

