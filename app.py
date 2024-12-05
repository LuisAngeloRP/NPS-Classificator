import streamlit as st
import pandas as pd
import openai
from time import sleep
import json

def create_system_prompt(taxonomy_df):
    # Crear un diccionario estructurado de la taxonomía
    taxonomy_dict = {}
    for _, row in taxonomy_df.iterrows():
        cat = row['Categoría']
        subcat = row['Subcategoría']
        detail = row['Detalle'] if row['Detalle'] != '-' else 'N/A'
        desc = row['Descripción']
        
        if cat not in taxonomy_dict:
            taxonomy_dict[cat] = {}
        if subcat not in taxonomy_dict[cat]:
            taxonomy_dict[cat][subcat] = {}
        taxonomy_dict[cat][subcat][detail] = desc

    # Crear el texto del prompt con énfasis en las descripciones
    taxonomy_text = "TAXONOMÍA Y GUÍA DE INTERPRETACIÓN:\n\n"
    for cat, subcats in taxonomy_dict.items():
        taxonomy_text += f"=== {cat} ===\n"
        for subcat, details in subcats.items():
            taxonomy_text += f"• {subcat}:\n"
            for detail, desc in details.items():
                if detail != "N/A":
                    taxonomy_text += f"  - {detail}: {desc}\n"
                else:
                    taxonomy_text += f"  {desc}\n"
            taxonomy_text += "\n"

    return f"""Eres un clasificador de comentarios de Yape que debe interpretar y categorizar el sentimiento y la intención del usuario.

{taxonomy_text}


INSTRUCCIONES DE CLASIFICACIÓN:
1. Usa las descripciones como guía para entender el contexto y la intención del usuario
2. Sé flexible en la interpretación, pero mantén la estructura de categorías existente
3. Considera sinónimos y expresiones alternativas que apunten a la misma intención
4. Prioriza el tema principal o la primera preocupación mencionada
5. Si detectas una intención clara, clasifícala aunque esté expresada de forma indirecta
6. Solo deja campos vacíos cuando realmente no hay forma de interpretar la intención

EJEMPLOS DE CLASIFICACIÓN FLEXIBLE:
"No me deja hacer nada" -> {{"categoria": "Problemas en la aplicación", "subcategoria": "Inestabilidad", "detalle": "N/A"}}
"Quisiera poder usarlo en más sitios" -> {{"categoria": "Accesibilidad", "subcategoria": "Capilaridad", "detalle": "N/A"}}
"Me limitan mucho las transferencias" -> {{"categoria": "Variedad de productos que faltan", "subcategoria": "Límite Transaccional", "detalle": "Límite Diario"}}
"Solo funciona con BCP" -> {{"categoria": "Variedad de productos que faltan", "subcategoria": "Otros productos", "detalle": "DNI/OEF"}}

Responde solo con el JSON:
{{"categoria": "categoría", "subcategoria": "subcategoría", "detalle": "detalle"}}"""

def validate_classification(classification, taxonomy_df):
    """Validates if the classification exists in the taxonomy"""
    exists = False
    for _, row in taxonomy_df.iterrows():
        category_match = row['Categoría'] == classification['categoria']
        subcategory_match = row['Subcategoría'] == classification['subcategoria']
        detail_match = (row['Detalle'] == classification['detalle']) or \
                      (row['Detalle'] == '-' and classification['detalle'] == 'N/A')
        
        if category_match and subcategory_match and detail_match:
            exists = True
            break
    
    return exists

def classify_comment(comment, client, system_prompt, taxonomy_df, retries=3):
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Classify this comment: {comment}"}
                ],
                temperature=0.1,  # Reduced temperature for more consistent results
                max_tokens=150
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Si todos los campos están vacíos, retornar directamente
            if not any([result['categoria'], result['subcategoria'], result['detalle']]):
                return result
            
            # Si hay algún campo con contenido, validar que la clasificación existe
            if validate_classification(result, taxonomy_df):
                return result
            else:
                # Si la clasificación no es válida, retornar campos vacíos
                return {"categoria": "", "subcategoria": "", "detalle": ""}
                
        except Exception as e:
            if attempt == retries - 1:
                st.error(f"Error processing comment: {str(e)}")
                return {"categoria": "", "subcategoria": "", "detalle": ""}
            sleep(1)

def main():
    st.title("Yape NPS Comment Classifier")
    
    # File upload for taxonomy
    st.subheader("1. Upload Taxonomy File")
    st.markdown("Required columns: **Categoría**, **Subcategoría**, **Detalle**, **Descripción**")
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
            required_taxonomy_columns = ['Categoría', 'Subcategoría', 'Detalle', 'Descripción']
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
                    
                    # Classify the comment
                    classification = classify_comment(row['comentario'], client, system_prompt, taxonomy_df)
                    
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