import json
import pickle
from dataclasses import dataclass

FILE_PATH = "./all_notes_1.json"
PICKLE_PATH = 'all_notes.pickle'


@dataclass
class SuccessNote:
    folder: str
    title: str
    plaintext: str
    note_id: int


@dataclass
class FailNote:
    folder: str
    title: str
    note_id: int


def readFile_cached():
    try:
        success_list, fail_list = pickle.load(open(PICKLE_PATH, "rb"))
        return success_list, fail_list
    except (OSError, IOError) as e:
        readFile_forced()
        success_list, fail_list = pickle.load(open(PICKLE_PATH, "rb"))
        return success_list, fail_list


def readFile_forced():
    with open(FILE_PATH, encoding='utf-8') as fh:
        all_notes: dict = json.load(fh)
        # ['version', 'file_path', 'backup_type', 'html', 'accounts', 'cloudkit_participants', 'folders', 'notes']

        print(f'총 ' + str(len(all_notes['notes'].items())) + '개')

        success_list: list[SuccessNote] = []
        fail_list: list[FailNote] = []
        for note in all_notes['notes'].items():
            if 'plaintext' in note[1]:
                success_list.append(SuccessNote(
                    note[1]['folder'], note[1]['title'], note[1]['plaintext'], note[1]['note_id']))
            else:
                fail_list.append(
                    FailNote(note[1]['folder'], note[1]['title'], note[1]['note_id']))
                # 일부 note에는 plaintext가 아예 안 담겨져있다.
                # ex) 23년 1월 0121 토
                # note_id: 1001 이후로 일부가 그런듯

    with open(PICKLE_PATH, 'wb') as fw:
        pickle.dump((success_list, fail_list), fw)
    
    return success_list, fail_list


if __name__ == "__main__":
    readFile_forced()
