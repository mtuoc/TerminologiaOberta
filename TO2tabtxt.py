import xml.etree.ElementTree as ET
import csv
import argparse
import sys
import re

def clean_and_split_term(term):
    """
    Cleans a term by removing content within square brackets [] and parentheses (),
    and then splits the resulting string by the pipe character (|).

    Args:
        term (str): The raw term string from the XML.

    Returns:
        list[str]: A list of cleaned, individual terms.
    """
    # 1. Remove content within parentheses () and square brackets []
    # This uses a regular expression to find and remove text between ( ) and [ ], non-greedily.
    # The '|' ensures we match both patterns.
    cleaned_term = re.sub(r'\s*\(.*?\)|\s*\[.*?\]', '', term).strip()

    # 2. Split the term by the pipe character (|)
    # This will return a list. If there is no '|', the list contains the single term.
    if '|' in cleaned_term:
        # Split and filter out any empty strings that might result from trailing/leading pipes
        split_terms = [t.strip() for t in cleaned_term.split('|') if t.strip()]
    else:
        # If no pipe, return the single cleaned term in a list, ensuring it's not empty
        split_terms = [cleaned_term] if cleaned_term else []
        
    return split_terms


def passes_filters(category, denomination_type, denomination_jerarquia, normalized_category_prefixes, normalized_type_filters, normalized_jerarquia_filter):
    """
    Checks if a denomination passes both the category prefix filter and the type filter.
    Returns True if the denomination is accepted, False otherwise.
    
    CRITICAL CHANGE: If a filter is active, but the denomination attribute (category or type) 
    is missing (empty string), it is now considered 'passed' (True) for that specific filter.
    Rejection only occurs if the attribute is PRESENT but fails to match the filter criteria.
    """
    category = category.strip().lower()
    denomination_type = denomination_type.strip().lower()
    denomination_jerarquia = denomination_jerarquia.strip().lower()

    # 1. Check Denomination Type Filter
    # If filter is active, only reject if the type is PRESENT but does not match.
    if normalized_type_filters:
        # Check only if denomination_type is NOT empty. If it's empty, we pass.
        if denomination_type and denomination_type not in normalized_type_filters:
            return False
        if denomination_jerarquia and denomination_jerarquia not in normalized_jerarquia_filters:
            return False
        
    # 2. Check Category Prefix Filter
    # If filter is active, only reject if the category is PRESENT but does not match any prefix.
    if normalized_category_prefixes:
        # Check only if category is PRESENT (not empty). If it's empty, we pass.
        if category:
            category_match = False
            for prefix in normalized_category_prefixes:
                if category.startswith(prefix):
                    category_match = True
                    break
            
            if not category_match:
                return False
            
    # If all active filters are passed, or attributes were missing when filters were active, return True
    return True


def xml_to_tsv(input_file, output_file, sl, tl, include_area, include_definition, include_category, category_prefixes, type_filters):
    """
    Converts an XML glossary file into a tab-separated values (TSV) file.
    
    It creates a separate entry for each combination of source term, 
    target term, and definition (to handle multiple senses/acceptions).

    Args:
        input_file (str): Name of the input XML file (e.g., 'glossary.xml').
        output_file (str): Name of the output TSV file (e.g., 'glossary_table.tsv').
        sl (str): Source language code (e.g., 'ca').
        tl (str): Target language code (e.g., 'es').
        include_area (bool): Whether to include the 'Thematic Area' column.
        include_definition (bool): Whether to include the 'Definition' column.
        include_category (bool): Whether to include the 'Category' (Part of Speech) column.
        category_prefixes (list, optional): List of category prefixes to filter by.
        type_filters (list, optional): List of denomination types to filter by (e.g., 'principal').
    """
    try:
        # Load and parse the XML file
        tree = ET.parse(input_file)
        root = tree.getroot()

    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        return
    except ET.ParseError:
        print(f"Error: Input file '{input_file}' is not a valid XML.")
        return
    except Exception as e:
        print(f"An unexpected error occurred during XML parsing: {e}")
        return

    # Prepare TSV content
    tsv_content = []
    
    # Pre-normalize filters if provided for efficient lookup
    normalized_type_filters = {f.strip().lower() for f in type_filters} if type_filters else None
    normalized_jerarquia_filters = {f.strip().lower() for f in jerarquia_filters} if type_filters else None
    normalized_category_prefixes = {p.strip().lower() for p in category_prefixes} if category_prefixes else None

    # Iterate over each <fitxa> (glossary entry)
    for entry in root.findall('.//fitxa'):
        
        # 1. Extract Thematic Area
        area_tematica = entry.findtext('areatematica', default='N/A').strip()

        # 2. Collect only the terms that pass the filters
        terms_sl_data = [] 
        terms_tl_data = []

        for denomination in entry.findall('denominacio'):
            language = denomination.get('llengua')
            raw_term = denomination.findtext('.', default='').strip()
            # Use .get with default='' to ensure we get an empty string, not None
            category = denomination.get('categoria', '').strip() 
            denomination_type = denomination.get('tipus', '').strip()
            denomination_jerarquia = denomination.get('jerarquia', '').strip()
            
            # --- APLICACIÓ DELS FILTRES INDIVIDUALS ---
            if passes_filters(category, denomination_type, denomination_jerarquia, normalized_category_prefixes, normalized_type_filters, normalized_type_filters):
                
                # Check for empty term
                if not raw_term:
                    continue 
                
                # --- NOU: Netejar i dividir els termes ---
                processed_terms = clean_and_split_term(raw_term)
                
                # If cleaning and splitting yielded no valid terms (e.g., only brackets remained), skip
                if not processed_terms:
                    continue
                
                # Store data for the corresponding language
                for term in processed_terms:
                    # The term, category, and type are stored together for the cross-join later.
                    # Note: The category/type is the same for all split terms from this single denomination tag.
                    if language == sl:
                        terms_sl_data.append((term, category, denomination_type))
                    elif language == tl:
                        terms_tl_data.append((term, category, denomination_type))
        
        # 3. Skip entry if no SL term passed the filters
        if not terms_sl_data:
            continue

        # --- PROCESSAMENT DE DEFINICIONS ---
        
        # Handle missing TL terms (if no TL term passed the filter, we still need to process the SL term(s))
        if not terms_tl_data:
            # Placeholder for TL term (term, category, type)
            terms_tl_data.append(('', '', ''))

        # 4. Collect all definitions for SL (acceptions/senses)
        definitions_sl = []
        if include_definition:
            for definition in entry.findall('definicio'):
                language = definition.get('llengua')
                if language == sl:
                    # Get definition text, clean newlines, and strip whitespace
                    text_definition = definition.findtext('.', default='').strip().replace('\n', ' ')
                    definitions_sl.append(text_definition if text_definition else '')
            
            # If the user requested definitions but none were found for SL, add a placeholder
            if not definitions_sl:
                definitions_sl.append('')
        else:
            # If definitions are not requested, treat the definition set as a single-element list for the cross-join
            definitions_sl.append(None)


        # 5. Create an entry for every combination (cross-join)
        
        # SL Terms (term_sl, category_sl, type_sl)
        for term_sl, category_sl, _ in terms_sl_data:
            
            # TL Terms (term_tl, category_tl, type_tl)
            for term_tl, category_tl, _ in terms_tl_data:
                
                # Definitions
                for definition_sl in definitions_sl:
                    
                    # Start the row with the mandatory terms (SL first, then TL)
                    row = [term_sl, term_tl]
                    
                    # Conditionally add Category (SL and TL)
                    if include_category:
                        # Append SL Category. Use empty string if not found.
                        row.append(category_sl if category_sl else '') 
                        # Append TL Category. Use empty string if not found.
                        row.append(category_tl if category_tl else '')
                    
                    # Conditionally build the rest of the row
                    if include_area:
                        # Append Thematic Area
                        row.append(area_tematica)
                    
                    if include_definition and definition_sl is not None:
                        # Append Definition
                        row.append(definition_sl)
                        
                    tsv_content.append(row)

    # 6. Write the content to the output file in TSV format
    try:
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            # Use 'excel-tab' dialect for tab delimiter
            writer = csv.writer(f, dialect='excel-tab')
            
            # Write the data rows (NO HEADER ROW)
            writer.writerows(tsv_content)
            
        print(f"\n Conversion completed successfully.")
        print(f"The tab-separated file has been saved to: **{output_file}**")
        print("-" * 40)
        print(f"Source Language (SL): **{sl.upper()}**")
        print(f"Target Language (TL): **{tl.upper()}**")
        print(f"Category included: **{include_category}**")
        if type_filters:
            print(f"Filtered by Denomination Type (Output): **{', '.join(type_filters).upper()}**")
        if category_prefixes:
            print(f"Filtered by Category Starts: **{', '.join(category_prefixes).upper()}**")
        print(f"Thematic Area included: **{include_area}**")
        print(f"Definition included: **{include_definition}**")

    except IOError:
        print(f"Error: Could not write to the output file '{output_file}'.")

# --- SCRIPT EXECUTION AND ARGPARSE SETUP ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Converts an XML glossary file into a tab-separated (TSV) file, handling multiple senses/acceptions. IMPORTANT: Both --category-starts and --type-filter are applied to every single denomination (SL and TL) during data collection.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # Required arguments using short flags
    parser.add_argument(
        '-i', '--input', 
        type=str, 
        required=True, 
        help="Input XML file path (e.g., 'wadfiateencatala.xml')."
    )
    parser.add_argument(
        '-o', '--output', 
        type=str, 
        required=True, 
        help="Output TSV file path (e.g., 'glossary_output.tsv')."
    )
    parser.add_argument(
        '--sl', 
        type=str, 
        required=True, 
        help="Source language code (e.g., 'ca'). This determines the FIRST column in the output."
    )
    parser.add_argument(
        '--tl', 
        type=str, 
        required=True, 
        help="Target language code (e.g., 'es')."
    )

    # Optional flags (defaulting to False)
    parser.add_argument(
        '--include-area', 
        action='store_true', 
        default=False, 
        help="Include the 'Thematic Area' column."
    )
    parser.add_argument(
        '--include-definition', 
        action='store_true', 
        default=False, 
        help="Include the 'Definition' column from the Source Language (SL)."
    )
    
    # --- Optionals for Category ---
    parser.add_argument(
        '--include-category',
        action='store_true', 
        default=False, 
        help="Include the 'Category' (Part of Speech, e.g., 'n f') for both SL and TL terms."
    )
    parser.add_argument(
        '--category-starts',
        nargs='+', # Accepts one or more arguments
        default=None,
        help="List of category prefixes (e.g., 'n', 'v', 'adj').\nOnly denominations whose category starts with one of these prefixes will be included.\nExample usage: --category-starts n v"
    )
    
    # --- ARGUMENT: Type Filter ---
    parser.add_argument(
        '--type-filter',
        nargs='+', # Accepts one or more arguments
        default=None,
        help="List of term 'tipus' (types) (e.g., 'principal', 'equivalent', 'remissió').\nOnly denominations that match one of these types will be included.\nExample usage: --type-filter principal preferent"
    )
    
    # --- ARGUMENT: Type Filter ---
    parser.add_argument(
        '--hierarchy-filter',
        nargs='+', # Accepts one or more arguments
        default=None,
        help="List of term 'hierarchy' (jerarquia) (e.g., 'terme pral.', 'var. ling.', 'sigla', 'abrev.', 'sin. compl.', 'den. com.' 'alt. sin.', 'den. desest.').\nOnly denominations that match one of these types will be included.\nExample usage: --type-filter principal preferent"
    )


    args = parser.parse_args()

    # Call the main function with arguments
    xml_to_tsv(
        args.input, 
        args.output, 
        args.sl, 
        args.tl, 
        args.include_area, 
        args.include_definition,
        args.include_category,
        args.category_starts,
        args.type_filter 
    )
