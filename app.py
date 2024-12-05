import streamlit as st
import pandas as pd
import openai
from time import sleep
import json

def create_system_prompt(taxonomy_df):
    # Create separate dictionaries for Promotores and Detractores+Pasivos
    promotor_dict = {}
    detractor_dict = {}
    
    for _, row in taxonomy_df.iterrows():
        cat = row['Categoría']
        subcat = row['Subcategoría']
        detail = row['Detalle'] if row['Detalle'] != '-' else 'N/A'
        desc = row['Descripción']
        tipo_nps = row['TIPO_NPS']
        
        target_dict = promotor_dict if tipo_nps == 'Promotor' else detractor_dict
        
        if cat not in target_dict:
            target_dict[cat] = {}
        if subcat not in target_dict[cat]:
            target_dict[cat][subcat] = {}
        target_dict[cat][subcat][detail] = desc

    taxonomy_text = "CATEGORÍAS POR TIPO DE COMENTARIO:\n\n"
    
    # Add categories for Promotores
    taxonomy_text += "=== CATEGORÍAS PARA COMENTARIOS DE PROMOTORES ===\n"
    for cat, subcats in promotor_dict.items():
        taxonomy_text += f"\n{cat}:\n"
        for subcat, details in subcats.items():
            taxonomy_text += f"• {subcat}:\n"
            for detail, desc in details.items():
                if detail != "N/A":
                    taxonomy_text += f"  - {detail}: {desc}\n"
                else:
                    taxonomy_text += f"  {desc}\n"
    
    # Add categories for Detractores+Pasivos
    taxonomy_text += "\n=== CATEGORÍAS PARA COMENTARIOS DE DETRACTORES Y PASIVOS ===\n"
    for cat, subcats in detractor_dict.items():
        taxonomy_text += f"\n{cat}:\n"
        for subcat, details in subcats.items():
            taxonomy_text += f"• {subcat}:\n"
            for detail, desc in details.items():
                if detail != "N/A":
                    taxonomy_text += f"  - {detail}: {desc}\n"
                else:
                    taxonomy_text += f"  {desc}\n"

    return f"""Eres un clasificador experto de comentarios de Yape especializado en análisis detallado de retroalimentación de usuarios. Tu objetivo es comprender profundamente el contexto y la intención detrás de cada comentario, especialmente para usuarios Detractores y Pasivos.

{taxonomy_text}

GUÍA DE ANÁLISIS PROFUNDO:

1. ANÁLISIS POR TIPO DE USUARIO:

   PARA DETRACTORES Y PASIVOS:
   - Identifica la causa raíz del problema o insatisfacción
   - Reconoce múltiples puntos de dolor si existen
   - Analiza el nivel de frustración en el lenguaje usado
   - Detecta problemas específicos mencionados implícitamente
   - Considera el contexto completo del comentario
   - Identifica si hay un problema técnico, de experiencia o de expectativas
   
   PARA PROMOTORES:
   - Identifica los aspectos específicos que elogian
   - Reconoce las características más valoradas

2. PAUTAS DE INTERPRETACIÓN AVANZADA:
   - Busca palabras clave que indiquen problemas específicos
   - Analiza el tono y la intensidad del comentario
   - Considera menciones indirectas de problemas
   - Identifica sugerencias de mejora implícitas
   - Relaciona quejas específicas con categorías más amplias
   - Presta especial atención a menciones de:
     * Problemas técnicos recurrentes
     * Experiencias negativas con el servicio
     * Comparaciones con otros servicios
     * Limitaciones o restricciones
     * Problemas de seguridad

3. REGLAS DE CLASIFICACIÓN:
   - Usa exclusivamente las categorías permitidas según el TIPO_NPS
   - Prioriza la categorización más específica disponible
   - Si hay múltiples problemas, selecciona el más crítico o impactante
   - Asegura que la clasificación refleje la verdadera causa del problema
   - Verifica que la subcategoría y el detalle sean coherentes con el problema principal

EJEMPLOS DE CLASIFICACIÓN DETALLADA:

DETRACTOR+PASIVO:
"La app se pone muy lenta cuando quiero hacer transferencias y a veces se cuelga" -> 
{{"categoria": "Velocidad", "subcategoria": "Navegación", "detalle": "N/A"}}

"Deberían aumentar los límites de transferencia, es muy poco lo que se puede mover por día" -> 
{{"categoria": "Variedad de productos que faltan", "subcategoria": "Límite Transaccional", "detalle": "Límite Diario"}}

"No me gusta que para cada cosa me pidan validar mi identidad, es muy tedioso" -> 
{{"categoria": "Experiencia", "subcategoria": "Validación de Identidad", "detalle": "N/A"}}

PROMOTOR:
"La velocidad de las transferencias es excelente" -> 
{{"categoria": "Velocidad", "subcategoria": "Navegación", "detalle": "N/A"}}

"Me encanta que todos mis amigos y familia usen Yape" -> 
{{"categoria": "Accesibilidad", "subcategoria": "Capilaridad", "detalle": "N/A"}}

Responde solo con el JSON:
{{"categoria": "categoría", "subcategoria": "subcategoría", "detalle": "detalle"}}"""

def classify_comment(comment, tipo_nps, client, system_prompt, taxonomy_df, retries=3):
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Classify this {tipo_nps} comment: {comment}"}
                ],
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Validar que la clasificación existe y corresponde al TIPO_NPS
            valid_classifications = taxonomy_df[taxonomy_df['TIPO_NPS'] == tipo_nps]
            if validate_classification(result, valid_classifications):
                return result
            else:
                return {"categoria": "", "subcategoria": "", "detalle": ""}
                
        except Exception as e:
            if attempt == retries - 1:
                st.error(f"Error processing comment: {str(e)}")
                return {"categoria": "", "subcategoria": "", "detalle": ""}
            sleep(1)

def validate_classification(classification, valid_df):
    """Validates if the classification exists in the allowed taxonomy"""
    exists = False
    for _, row in valid_df.iterrows():
        category_match = row['Categoría'] == classification['categoria']
        subcategory_match = row['Subcategoría'] == classification['subcategoria']
        detail_match = (row['Detalle'] == classification['detalle']) or \
                      (row['Detalle'] == '-' and classification['detalle'] == 'N/A')
        
        if category_match and subcategory_match and detail_match:
            exists = True
            break
    
    return exists

def main():
    st.title("Yape NPS Comment Classifier")
    
    # File upload for taxonomy
    st.subheader("1. Upload Taxonomy File")
    st.markdown("Required columns: **Categoría**, **Subcategoría**, **Detalle**, **Descripción**, **TIPO_NPS**")
    taxonomy_file = st.file_uploader("Upload taxonomy Excel file", type=['xlsx'], key="taxonomy")
    
    # File upload for comments
    st.subheader("2. Upload Comments File")
    st.markdown("Required columns: **TIPO_NPS**, **comentario**")
    comments_file = st.file_uploader("Upload comments Excel file", type=['xlsx'], key="comments")
    
    if taxonomy_file and comments_file:
        try:
            # Get API key from secrets
            api_key = st.secrets["openai"]["api_key"]
            
            # Read the Excel files
            taxonomy_df = pd.read_excel(taxonomy_file)
            comments_df = pd.read_excel(comments_file)
            
            # Validate required columns
            required_taxonomy_columns = ['Categoría', 'Subcategoría', 'Detalle', 'Descripción', 'TIPO_NPS']
            required_comments_columns = ['TIPO_NPS', 'comentario']
            
            if not all(col in taxonomy_df.columns for col in required_taxonomy_columns):
                st.error(f"Taxonomy file must contain columns: {', '.join(required_taxonomy_columns)}")
                return
                
            if not all(col in comments_df.columns for col in required_comments_columns):
                st.error(f"Comments file must contain columns: {', '.join(required_comments_columns)}")
                return
            
            if st.button("Process Comments"):
                client = openai.OpenAI(api_key=api_key)
                system_prompt = create_system_prompt(taxonomy_df)
                
                # Initialize progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Process each comment
                results = []
                total_comments = len(comments_df)
                
                for idx, row in comments_df.iterrows():
                    # Update progress
                    progress = (idx + 1) / total_comments
                    progress_bar.progress(progress)
                    status_text.text(f"Processing comment {idx + 1} of {total_comments}")
                    
                    # Classify the comment - Ahora pasamos el TIPO_NPS y taxonomy_df
                    classification = classify_comment(
                        comment=row['comentario'],
                        tipo_nps=row['TIPO_NPS'],
                        client=client,
                        system_prompt=system_prompt,
                        taxonomy_df=taxonomy_df
                    )
                    
                    # Add to results
                    result_row = {
                        'TIPO_NPS': row['TIPO_NPS'],
                        'comentario': row['comentario'],
                        'TAB1': classification['categoria'],
                        'TAB2': classification['subcategoria'],
                        'TAB3': classification['detalle']
                    }
                    results.append(result_row)
                
                # Create final dataframe
                result_df = pd.DataFrame(results)
                
                # Display results
                st.subheader("Results")
                st.dataframe(result_df)
                
                # Download button for CSV
                st.download_button(
                    label="Download Results (CSV)",
                    data=result_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'),
                    file_name="classified_comments.csv",
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()