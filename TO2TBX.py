import xml.etree.ElementTree as ET
import argparse
from datetime import datetime
import sys
import re

# ==============================================================================
# 1. HELPER FUNCTIONS
# ==============================================================================

# Register the 'xml' namespace for 'xml:lang'
ET.register_namespace('xml', "http://www.w3.org/XML/1998/namespace")

def indent(elem, level=0, space="  "):
    """Formats the XML tree for readability (pretty print)."""
    i = "\n" + level * space
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + space
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level + 1, space)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if not elem.tail or not elem.tail.strip():
            elem.tail = i

def clean_and_split_term(term):
    """Cleans a term by removing content within parentheses/brackets and splits it by '|'."""
    # Clean: remove content within ( ) or [ ]
    cleaned_term = re.sub(r'\s*\(.*?\)|\s*\[.*?\]', '', term).strip()
    
    # Split: split by '|'
    if '|' in cleaned_term:
        split_terms = [t.strip() for t in cleaned_term.split('|') if t.strip()]
    else:
        split_terms = [cleaned_term] if cleaned_term else []
    return split_terms

def normalize_filter_list(filter_list):
    """Normalizes a list of filter strings into a set (lowercase)."""
    if not filter_list:
        return None
    # Convert to lowercase and strip whitespace
    normalized_set = {f.strip().lower() for f in filter_list if f.strip()}
    return normalized_set if normalized_set else None

def passes_filters(category, denomination_type, denomination_jerarquia, 
                   normalized_category_prefixes, normalized_type_filters, normalized_jerarquia_filter):
    """Checks if a denomination passes all applied filters (Category, Type, Hierarchy)."""
    
    # 1. Category Prefix Filter
    if normalized_category_prefixes:
        category = category.strip().lower()
        if not category or not any(category.startswith(prefix) for prefix in normalized_category_prefixes):
            return False
            
    # 2. Type Filter (tipus)
    if normalized_type_filters:
        denomination_type = denomination_type.strip().lower()
        if denomination_type not in normalized_type_filters:
            return False

    # 3. Hierarchy Filter (jerarquia)
    if normalized_jerarquia_filter:
        denomination_jerarquia = denomination_jerarquia.strip().lower()
        if denomination_jerarquia not in normalized_jerarquia_filter:
            return False
            
    return True


# ==============================================================================
# 2. MAIN CONVERSION LOGIC
# ==============================================================================

def xml_to_tbx(input_file, output_file, sl, tl, 
               include_area, include_definition, include_category, 
               category_starts, type_filter, hierarchy_filter):
    """
    Converts an XML glossary file into a TermBase eXchange (TBX) file,
    with optional filtering and inclusion of various data fields.
    """
    print(f"Starting XML to TBX conversion for {input_file}...")
    
    # --- 1. TBX Structure Setup ---
    NS_TBX = "urn:iso:std:iso:61440:TBX-core" 
    NS_XML = "http://www.w3.org/XML/1998/namespace"
    
    martif = ET.Element('martif', attrib={'type': 'TBX', 'version': '2.0', 'xmlns': NS_TBX, 'xmlns:xml': NS_XML})
    
    # martifHeader
    martifHeader = ET.SubElement(martif, 'martifHeader')
    fileDesc = ET.SubElement(martifHeader, 'fileDesc')
    ET.SubElement(fileDesc, 'titleStmt').text = f"TBX Conversion from {input_file}"
    ET.SubElement(fileDesc, 'pubStmt')
    encodingDesc = ET.SubElement(martifHeader, 'encodingDesc')
    ET.SubElement(encodingDesc, 'encoding', attrib={'ref': 'UTF-8', 'name': 'UNICODE'})
    creationDate = ET.SubElement(martifHeader, 'creationDate')
    creationDate.set('date', datetime.now().strftime("%Y-%m-%d"))

    # text body
    text = ET.SubElement(martif, 'text')
    body = ET.SubElement(text, 'body')

    # --- 2. Load and Parse XML ---
    try:
        tree = ET.parse(input_file)
        root = tree.getroot()
        print(f"Successfully loaded XML file.")
    except FileNotFoundError:
        print(f"Error: Input file not found: {input_file}", file=sys.stderr)
        return
    except Exception as e:
        print(f"Error during XML parsing: {e}", file=sys.stderr)
        return

    # --- 3. Normalize Filters ---
    normalized_category_prefixes = normalize_filter_list(category_starts)
    normalized_type_filters = normalize_filter_list(type_filter)
    normalized_jerarquia_filter = normalize_filter_list(hierarchy_filter)
    
    entry_count = 0
    exported_entries = 0
    
    # --- 4. Iterate and Convert ---
    
    # Find all <fitxa> elements throughout the tree
    for entry in root.findall('.//fitxa'):
        entry_count += 1
        entry_id = entry.get('num', f'e{entry_count}')
        
        # 4.1 Extract entry-level fields
        area_tematica = entry.findtext('areatematica', default='').strip()
        
        definitions = {}
        # Collect definitions only for SL and TL
        # The prompt only requires the SL definition to be exported, but we collect both for flexibility.
        for definition in entry.findall('definicio'):
            language = definition.get('llengua', '').strip().lower()
            text_content = definition.findtext('.', default='').strip()
            if text_content and language in [sl, tl]:
                definitions[language] = text_content
        
        # 4.2 Group all denominations by language and apply filters
        denominations_by_lang = {sl: [], tl: []}
        
        # Check if the entire fitxa is valid (i.e., if it contains at least one SL term 
        # that passes ALL filters AND has at least one term in the target language)
        has_valid_sl_term = False
        
        # Pass 1: Collect ALL terms and filter them *individually*
        all_denominations = entry.findall('denominacio')
        
        for denomination in all_denominations:
            language = denomination.get('llengua', '').strip().lower()
            raw_term = denomination.findtext('.', default='').strip()
            
            # Extract denomination fields
            category = denomination.get('categoria', '').strip() 
            denomination_type = denomination.get('tipus', '').strip()
            denomination_jerarquia = denomination.get('jerarquia', '').strip()
            
            if language not in [sl, tl] or not raw_term:
                continue
            
            # Apply all filters to the denomination
            if not passes_filters(category, denomination_type, denomination_jerarquia, 
                                  normalized_category_prefixes, normalized_type_filters, normalized_jerarquia_filter):
                continue # Skip this denomination if it fails any filter
            
            # If an SL denomination passes the filters, the entire entry is considered valid for export
            if language == sl:
                has_valid_sl_term = True 
                
            # Clean and split terms (e.g., handling variants separated by '|')
            processed_terms = clean_and_split_term(raw_term)
            
            for term in processed_terms:
                denominations_by_lang[language].append({
                    'term': term,
                    'category': category,
                    'type': denomination_type,
                    'hierarchy': denomination_jerarquia
                })
        
        # Final filter: The entry must contain at least one SL term that passed the filters
        if not has_valid_sl_term or not denominations_by_lang.get(tl):
            continue

        # 4.3 Generate TBX <termEntry>
        termEntry = ET.SubElement(body, 'termEntry', attrib={'id': entry_id})
        exported_entries += 1
        
        # Add descriptive fields at the entry level
        if include_area and area_tematica:
            descrip = ET.SubElement(termEntry, 'descrip', attrib={'type': 'subject'})
            descrip.text = area_tematica
        
        # Process each language (SL first, then TL)
        for lang_code in [sl, tl]:
            
            # Only proceed if the language has terms OR if it's the SL and we include the definition
            if denominations_by_lang.get(lang_code) or (include_definition and lang_code == sl and sl in definitions):
                langSet = ET.SubElement(termEntry, 'langSet', attrib={'xml:lang': lang_code})

                # Add definition (only from SL, as per the help text in the prompt)
                if include_definition and lang_code == sl and sl in definitions and definitions[sl]:
                    descrip_def = ET.SubElement(langSet, 'descrip', attrib={'type': 'definition'})
                    descrip_def.text = definitions[sl]
                
                # Add all terms for this language
                for d in denominations_by_lang.get(lang_code, []):
                    tig = ET.SubElement(langSet, 'tig')
                    
                    term = ET.SubElement(tig, 'term')
                    term.text = d['term']
                    
                    # Category (Part of Speech)
                    if include_category and d['category']:
                        termNote_cat = ET.SubElement(tig, 'termNote', attrib={'type': 'partOfSpeech'})
                        termNote_cat.text = d['category']

                    # Type (Term Type)
                    # NOTE: This is always included if the term passed the filter, but the inclusion flag 
                    # for <termNote> depends on whether the filter was active. We'll include it only if the filter was used.
                    if type_filter and d['type']:
                        termNote_type = ET.SubElement(tig, 'termNote', attrib={'type': 'termType'})
                        termNote_type.text = d['type']

                    # Hierarchy (Normative Authorization)
                    # NOTE: Included only if the filter was active.
                    if hierarchy_filter and d['hierarchy']:
                        termNote_hier = ET.SubElement(tig, 'termNote', attrib={'type': 'normativeAuthorization'})
                        termNote_hier.text = d['hierarchy']


    # --- 5. Finalize and Save TBX ---
    indent(martif)

    try:
        tree = ET.ElementTree(martif)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)

    except IOError:
        print(f"Error: Could not write to the output file '{output_file}'. Check permissions.", file=sys.stderr)
        return
    except Exception as e:
        print(f"An unexpected error occurred during writing: {e}", file=sys.stderr)
        return

    # --- 6. Summary Message ---
    print("-" * 50)
    print(f"XML entries processed: {entry_count}. TBX entries generated: {exported_entries}.")
    
    if exported_entries == 0:
        print("Warning: No TBX entries were generated. Please check your filters and language codes.")

    print(f"✅ TBX conversion completed successfully. File saved to: {output_file}")
    print("-" * 50)


# ==============================================================================
# 3. ARGPARSE CONFIGURATION (All Named Arguments)
# ==============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Convert an XML glossary file (e.g., TERMCAT format) into a TBX Termbase file (TBX-core 2.0).",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # --- Required Arguments (now using -i/-o and --sl/--tl) ---
    parser.add_argument(
        '-i', '--input', 
        type=str, 
        required=True,
        help="Input XML file path (e.g., 'glossary.xml')."
    )
    parser.add_argument(
        '-o', '--output', 
        type=str, 
        required=True,
        help="Output TBX file path (e.g., 'termbase.tbx')."
    )
    parser.add_argument(
        '--sl', 
        type=str, 
        required=True,
        help="Source language code (e.g., 'ca')."
    )
    parser.add_argument(
        '--tl', 
        type=str, 
        required=True,
        help="Target language code (e.g., 'es')."
    )

    # --- Optional Inclusion Flags ---
    inclusion_group = parser.add_argument_group('Inclusion Options', 'Flags to include optional fields from the XML in the TBX file.')
    
    inclusion_group.add_argument(
        '--include-area', 
        action='store_true', 
        default=False, 
        help="Include the Thematic Area (<areatematica>) as <descrip type=\"subject\">."
    )
    inclusion_group.add_argument(
        '--include-definition', 
        action='store_true', 
        default=False, 
        help="Include the Definition (from SL) as <descrip type=\"definition\">."
    )
    inclusion_group.add_argument(
        '--include-category',
        action='store_true', 
        default=False, 
        help="Include the term's category (<categoria>, e.g., 'n f') as <termNote type=\"partOfSpeech\">. This is *required* to apply the category filter."
    )
    
    # --- Optional Filter Arguments ---
    filter_group = parser.add_argument_group('Filtering Options', 'Filters are applied to ALL denominations in the TBX file. Only denominations that satisfy ALL active filters are included.')

    filter_group.add_argument(
        '--category-starts',
        nargs='+', # Accepts one or more arguments
        default=None,
        help=("List of category prefixes (e.g., 'n', 'v', 'adj').\n"
              "Only denominations whose category starts with one of these prefixes will be included.\n"
              "Example usage: --category-starts n m f")
    )
    
    filter_group.add_argument(
        '--type-filter',
        nargs='+', 
        default=None,
        help=("List of term 'tipus' (types) (e.g., 'principal', 'equivalent', 'remissió').\n"
              "Only denominations that match one of these types will be included.\n"
              "Example usage: --type-filter principal preferent")
    )

    filter_group.add_argument(
        '--hierarchy-filter',
        nargs='+', 
        default=None,
        help=("List of term 'hierarchy' (jerarquia) (e.g., 'terme pral.', 'sigla').\n"
              "Only denominations that match one of these hierarchies will be included.\n"
              "Example usage: --hierarchy-filter terme pral. var. ling.")
    )


    args = parser.parse_args()

    # Call the main function with arguments
    xml_to_tbx(
        args.input, 
        args.output, 
        args.sl.lower(), 
        args.tl.lower(), 
        args.include_area, 
        args.include_definition, 
        args.include_category,
        args.category_starts, 
        args.type_filter, 
        args.hierarchy_filter
    )
