import xml.etree.ElementTree as ET
import argparse
from datetime import datetime
import sys

# Add the 'xml' namespace for 'xml:lang'
ET.register_namespace('xml', "http://www.w3.org/XML/1998/namespace")

# Function to indent (pretty print) an ElementTree, compatible with Python < 3.9
def indent(elem, level=0, space="  "):
    """
    Format the XML tree for readability (simulating pretty print).
    Based on standard library implementation details.
    """
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

def xml_to_tbx(input_file, output_file, sl, tl, include_area, include_definition, category_prefixes, include_category):
    """
    Converts an XML glossary file into a TermBase eXchange (TBX) file,
    with optional filtering and inclusion of various data fields.
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
        print(f"An unexpected error occurred during file parsing: {e}")
        return

    # --- 1. TBX Structure Setup ---
    
    # Define the TBX namespace and the root element
    TBX_NS = "urn:iso:std:iso:4466:tbx:v1"
    
    # Register the default namespace
    ET.register_namespace('', TBX_NS) 
    
    # Create the root <martif> element
    martif = ET.Element(
        'martif', 
        {
            'type': "TBX", 
            # Use 'xml:lang' namespace prefix
            '{http://www.w3.org/XML/1998/namespace}lang': sl.lower()
        }
    )
    
    # Create the <martifHeader>
    martif_header = ET.SubElement(martif, 'martifHeader')
    file_desc = ET.SubElement(martif_header, 'fileDesc')
    title_stmt = ET.SubElement(file_desc, 'titleStmt')
    ET.SubElement(title_stmt, 'title').text = "TBX Conversion from Glossary XML"
    
    source_desc = ET.SubElement(file_desc, 'sourceDesc')
    ET.SubElement(source_desc, 'p').text = f"Source XML file: {input_file}"
    
    encoding_desc = ET.SubElement(martif_header, 'encodingDesc')
    ET.SubElement(encoding_desc, 'p').text = f"File generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


    # Create <text> and <body/termEntry> which holds the actual data
    text = ET.SubElement(martif, 'text')
    body = ET.SubElement(text, 'body')
    
    
    # --- 2. Data Processing and TBX Generation ---
    
    entry_counter = 0

    # Iterate over each <fitxa> (glossary entry)
    for entry in root.findall('.//fitxa'):
        
        # Collect terms and definitions (acceptions) grouped by language
        terms_sl_data = [] # Stores (term_text, category_text)
        terms_tl_data = [] # Stores (term_text, category_text)
        definitions_sl = []
        
        # --- Data Collection: Terms and Categories ---
        for denomination in entry.findall('denominacio'):
            language = denomination.get('llengua')
            term = denomination.findtext('.', default='').strip()
            category = denomination.get('categoria', '').strip() # Get category here
            
            if language == sl:
                terms_sl_data.append((term, category))
            elif language == tl:
                terms_tl_data.append((term, category))

        # --- Filtering Logic ---
        if category_prefixes:
            # Find the category of the principal term in SL for filtering
            principal_sl_category = next((cat for term, cat in terms_sl_data if entry.find(f".//denominacio[@llengua='{sl}'][@tipus='principal']") is not None and entry.find(f".//denominacio[@llengua='{sl}'][@tipus='principal']").text == term), '').strip().lower()
            
            category_match = False
            if principal_sl_category:
                for prefix in category_prefixes:
                    if principal_sl_category.startswith(prefix.strip().lower()):
                        category_match = True
                        break
            
            # If a filter is active and no match is found, skip this entry
            if not category_match:
                continue
        # --- End Filtering Logic ---

        # If the entry passes the filter (or no filter was applied), process it
        entry_counter += 1
        
        # Extract Thematic Area once per entry
        area_tematica = entry.findtext('areatematica', default='').strip()
        
        # --- Data Collection: Definitions ---
        if include_definition:
            for definition in entry.findall('definicio'):
                language = definition.get('llengua')
                if language == sl:
                    # Clean newlines and strip whitespace
                    text_definition = definition.findtext('.', default='').strip().replace('\n', ' ')
                    definitions_sl.append(text_definition)
        
        # Validation and Placeholder lists
        if not terms_sl_data:
            continue # Should be rare due to filtering logic, but safety check

        if include_definition:
            if not definitions_sl:
                definitions_sl.append('') 
        else:
            definitions_sl.append(None) 
            
        if not terms_tl_data:
            terms_tl_data.append(('', '')) # Empty term, empty category

        # We use the list of definitions to define the number of concept/acceptions
        for i, definition_sl in enumerate(definitions_sl):
            
            # --- TBX: <termEntry> ---
            term_entry = ET.SubElement(body, 'termEntry', {'id': f"e-{entry_counter}-{i+1}"})

            # --- TBX: Thematic Area (Subject) ---
            if include_area and area_tematica:
                subject_desc = ET.SubElement(term_entry, 'descrip', {'type': "subject"})
                subject_desc.text = area_tematica

            # --- TBX: Language Section for SL ---
            lang_sec_sl = ET.SubElement(term_entry, 'langSet', {'xml:lang': sl})
            
            # 5. Add Terms and Definitions for SL
            for term_sl, category_sl in terms_sl_data: 
                if not term_sl: continue
                # <tig> for term information group
                tig = ET.SubElement(lang_sec_sl, 'tig')
                # <term>
                ET.SubElement(tig, 'term').text = term_sl
                
                # --- NEW: Include Category ---
                if include_category and category_sl:
                    # Use termNote with type="partOfSpeech" for category
                    ET.SubElement(tig, 'termNote', {'type': "partOfSpeech"}).text = category_sl

                # <descrip type="definition">
                if include_definition and definition_sl is not None:
                    if definition_sl:
                        def_desc = ET.SubElement(tig, 'descrip', {'type': "definition"})
                        def_desc.text = definition_sl
            
            # --- TBX: Language Section for TL ---
            lang_sec_tl = ET.SubElement(term_entry, 'langSet', {'xml:lang': tl})
            
            # 6. Add Terms for TL
            for term_tl, category_tl in terms_tl_data: 
                if not term_tl: continue
                # <tig> for term information group
                tig = ET.SubElement(lang_sec_tl, 'tig')
                # <term>
                ET.SubElement(tig, 'term').text = term_tl
                
                # --- NEW: Include Category for TL (if available) ---
                if include_category and category_tl:
                    ET.SubElement(tig, 'termNote', {'type': "partOfSpeech"}).text = category_tl
    
    # --- 3. Write TBX File ---
    try:
        # Indent the whole tree for readability
        indent(martif) 
        
        # Create an ElementTree object
        output_tree = ET.ElementTree(martif)
        
        # Write the file
        output_tree.write(
            output_file, 
            encoding='UTF-8', 
            xml_declaration=True
        )
        
        # Print Summary (Now fully in English)
        print("-" * 40)
        print(f"✅ Conversion completed successfully.")
        print(f"TBX file saved to: **{output_file}**")
        print(f"Total entries processed and written: **{entry_counter}**")
        print("-" * 40)
        print(f"Source Language (SL): **{sl.upper()}**")
        print(f"Target Language (TL): **{tl.upper()}**")
        print(f"Thematic Area included: **{include_area}**")
        print(f"Definition included: **{include_definition}**")
        print(f"Category included: **{include_category}**")
        if category_prefixes:
            print(f"Filtered by Category Starts: **{', '.join(category_prefixes).upper()}**")

    except IOError:
        print(f"Error: Could not write to the output file '{output_file}'. Check permissions or path.")
    except Exception as e:
        print(f"An unexpected error occurred during file writing: {e}")

# --- SCRIPT EXECUTION AND ARGPARSE SETUP ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Converts an XML glossary file into a standard TBX (TermBase eXchange) file.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # Required arguments using short flags
    parser.add_argument(
        '-i', '--input', 
        type=str, 
        required=True, 
        help="Input XML file path (e.g., 'source.xml')."
    )
    parser.add_argument(
        '-o', '--output', 
        type=str, 
        required=True, 
        help="Output TBX file path (e.g., 'glossary_output.tbx')."
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

    # Optional flags (defaulting to False)
    parser.add_argument(
        '--include-area', 
        action='store_true', 
        default=False, 
        help="Include the Thematic Area as <descrip type=\"subject\">."
    )
    parser.add_argument(
        '--include-definition', 
        action='store_true', 
        default=False, 
        help="Include the Definition (from SL) as <descrip type=\"definition\">."
    )
    
    # --- NEW ARGUMENT: Include Category ---
    parser.add_argument(
        '--include-category',
        action='store_true', 
        default=False, 
        help="Include the term's category (part of speech, e.g., 'n m') as <termNote type=\"partOfSpeech\">."
    )
    
    # Existing Category Filter Argument
    parser.add_argument(
        '--category-starts',
        nargs='+', # Accepts one or more arguments
        default=None,
        help="List of category prefixes (e.g., 'n', 'v', 'adj').\nOnly terms whose principal SL category starts with one of these prefixes will be included.\nExample usage: --category-starts n m f"
    )

    args = parser.parse_args()

    # Call the main function with arguments
    xml_to_tbx(
        args.input, 
        args.output, 
        args.sl, 
        args.tl, 
        args.include_area, 
        args.include_definition,
        args.category_starts,
        args.include_category # Pass the new argument
    )
