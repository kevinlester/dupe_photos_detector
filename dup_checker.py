from PIL import Image, ExifTags
from pathlib import Path
import os
import sqlite3
import sys
import subprocess
from collections import defaultdict
import shutil

photo_extensions = [".jpg", ".jpeg"]

'''
Why 31 years in the date query?  The reference date for IOS dates are from
2001-01-01, which is 31 years from the normal 1970-01-01. [https://stackoverflow.com/questions/10705062/behind-the-scenes-core-data-dates-stored-with-31-year-offset]
'''
def loadPhotoLibraryData(db_path):
    photo_library_data = {}
    photo_library_data['filename'] = defaultdict(list)
    photo_library_data['filesize'] = defaultdict(list)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        select 
            ga.Z_PK, 
            aa.ZORIGINALFILENAME as FileNameOriginal, 
            aa.ZORIGINALFILESIZE as FileSizeOriginal, 
            aa.ZORIGINALHEIGHT as HeightOriginal, 
            aa.ZORIGINALWIDTH as WidthOriginal,
            datetime(ga.ZDATECREATED,'unixepoch','31 years','localtime') as DateTimeOriginal,
            datetime(ga.ZMODIFICATIONDATE,'unixepoch','31 years','localtime') as ModicationDate,
            ga.ZDIRECTORY as LocalDirectory,
            ga.ZFILENAME as LocalFileName,
            ga.ZDIRECTORY || '/' || REPLACE(ga.ZFILENAME, '.jpeg', '_4_5005_c.jpeg') as FilePath
        from
            ZADDITIONALASSETATTRIBUTES aa
            JOIN ZGENERICASSET ga ON aa.ZASSET = ga.Z_PK
        ''')
    for row in c.fetchall():
        row_dict = dict(row)
        photo_library_data['filename'][row_dict['FileNameOriginal']].append(row_dict)
        photo_library_data['filesize'][row_dict['FileSizeOriginal']].append(row_dict)
    conn.close()
    return photo_library_data


def format_exif_val(tag, val):
    if (tag == 'DateTimeOriginal'):
        return val.replace(':', '-', 2)
    return repr(val)


def get_exif(entry_path):
    photo_exif = Image.open(str(entry_path)).getexif()
    photo_exif_dict = dict()
    for key, val in dict(photo_exif).items():
        if key in ExifTags.TAGS:
            tag = ExifTags.TAGS[key]
            photo_exif_dict[tag] = format_exif_val(tag, val)
    return photo_exif_dict


'''
def get_exif(photo_path):
    output = subprocess.run(['mdls', './_P9A0286-2.jpg'], stdout=subprocess.PIPE).stdout.decode('utf-8')
    print(output)
    md_dict = dict()
    mdData_list = [k.split('=') for k in output.split('\n')]

    md_iter = iter(mdData_list)
    val = next(md_iter, None)
    while (val != None):
        if (val == ['']): # this is the last line of input
            break
        if (len(val) != 2): # this is never expected to occur
            print(f'Unknown state: "{val}"')
            exit()
        if (val[1].strip() == '('): # we have a list of items for this key
            nested_list = []
            nested_list_val = next(md_iter, None)
            while (nested_list_val != None):
                if (len(nested_list_val) != 1):
                    print(f'New value type! {nested_list_val}')
                    exit()
                nested_val = nested_list_val[0].strip()
                if (nested_val == ')'):
                    break
                nested_list.append(nested_val)
                nested_list_val = next(md_iter, None)
            md_dict[val[0].strip()] = nested_list
        else:
            md_dict[val[0].strip()] = val[1].strip()
        val = next(md_iter, None)
    return md_dict
'''


def match_photo(photo_library_data, filepath, photo_exif):
    if ('DateTimeOriginal' not in photo_exif):
        print(f'{filepath.name}.  No exif date!')
        #print(photo_exif)
        return (None, None)
    print(f'{filepath.name}: exif date = ' + photo_exif['DateTimeOriginal'])
    # Try the best matches
    potential_matches = photo_library_data['filename'][filepath.name]
    best_match = None
    for potential_match in potential_matches:
        if (potential_match['FileSizeOriginal'] == filepath.stat().st_size):
            if (potential_match['DateTimeOriginal'] == photo_exif['DateTimeOriginal']):
                print('******** Exact ********')
                return ('EXACT', potential_match)
            print('******** Different Date ********')
            best_match = potential_match
    if (best_match is not None):
        return ('DIFF DATE', best_match)

    # Try the next level of matches
    potential_matches = photo_library_data['filesize'][filepath.name]
    best_match = None
    for potential_match in potential_matches:
        if (potential_match['DateTimeOriginal'] == photo_exif['DateTimeOriginal']):
            # different name, but samze size and creation date
            return ('DIFF NAME', potential_match)
    if (len(potential_matches) > 0):
        if (len(potential_matches) == 1):
            return ('Size Match', potential_match[0])
        print('******** SIZE MATCH ONLY ********')
    return (None, None)


def scan_dir(dir_to_scan):
    count = 0
    for entry in os.scandir(dir_to_scan):
        entry_path = Path(entry.path)
        if (entry_path.suffix.lower() in photo_extensions):
            photo_exif = get_exif(entry_path)
            match_photo(photo_library_data, entry_path, photo_exif)
            count = count + 1
        if (count >= 1000):
            break


def write_html_match(match_file, entry_path, match): 
    match_filepath = ROOT_PATH + 'resources/derivatives/masters/' + match['FilePath']
    match_cache_path = IMG_CACHE_PATH + '/' + match['FilePath']
    os.makedirs(os.path.dirname(match_cache_path), exist_ok=True)
    shutil.copy(match_filepath, match_cache_path)

    match_file.write(f'<div class="row">\n')
    match_file.write(f'  <div class="column">\n')
    match_file.write(f'    <img src="{entry_path}" style="width:100%">\n')
    match_file.write(f'  </div>\n')
    match_file.write(f'  <div class="column">\n')
    match_file.write(f'    <img src="{match_cache_path}" style="width:100%">\n')
    match_file.write(f'  </div>\n')
    match_file.write(f'</div>\n')


def close_match_file(match_file):
    match_file.write('</body>\n' )
    match_file.write('</html>\n')


ROOT_PATH = sys.argv[1]
SEARCH_PATH = sys.argv[2]
IMG_CACHE_PATH = './img_cache'

if __name__ == "__main__":
    db_path = ROOT_PATH + 'database/Photos.sqlite'
    Path(IMG_CACHE_PATH).mkdir(parents=True, exist_ok=True)
    photo_library_data = loadPhotoLibraryData(db_path)
    matches = defaultdict(list)
    shutil.copy('./templates/matches.html', './exact_matches.html')
    with open("./exact_matches.html", "a") as exact_match_file: 
        count = 0
        for entry in os.scandir(SEARCH_PATH):
            entry_path = Path(entry.path)
            if (entry_path.suffix.lower() in photo_extensions):
                photo_exif = get_exif(entry_path)
                match_type, match = match_photo(photo_library_data, entry_path, photo_exif)
                if (match_type is not None):
                    matches[match_type].append([exact_match_file, entry_path, match])
                count = count + 1
            if (count == 1000):
                for match_type, match_list in matches.items():
                    exact_match_file.write(f'<h2>{match_type} Duplicates</h2>\n')
                    for exact_match_file, entry_path, match in match_list:
                        write_html_match(exact_match_file, entry_path, match)
                    exact_match_file.write(f'<br/><br/>\n')
                close_match_file(exact_match_file)
                exit()
        close_match_file(exact_match_file)

    # Good so far to here.  Need to implement the matching logic.
    # exact match = same filename, size, and creation date.
    # partial match = same filename, size, but different creation date.
    # partial match = different filename, but same size, height, width, and creation date.
    # for each, output an html file so that I can see the candidate and the library dile side by side for decision making.
