import time
from filereader import readFile_cached, readFile_forced
from dotenv import dotenv_values
from notion_client import AsyncClient
from pprint import pprint
from dotmap import DotMap
import asyncio
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


config = dotenv_values(".env")
notion = AsyncClient(auth=config.get('NOTION_KEY'))
ROOT_PAGE: str = config.get('NOTION_PAGE_ID_ROOT') or 'ERROR'


# region notion objects


def parent(page_id: str, is_page=False):
    '''notion objects'''
    if is_page:
        return {
            "type": "page_id",
            "page_id": page_id
        }
    else:
        return {
            "type": "database_id",
            "database_id": page_id
        }


def rich_text(text: str):
    '''notion objects'''
    return {
        "type": "text",
                "text": {
                    "content": text,
                    "link": None
                },
        "annotations": {
                    "bold": False,
                    "italic": False,
                    "strikethrough": False,
                    "underline": False,
                    "code": False,
                    "color": "default"
                },
        "plain_text": text,
    }


def block(text: str):
    '''notion objects'''
    return {
        'object': 'block',
        'paragraph': {
            'rich_text': [rich_text(text)],
            "color": "default",
        }
    }


def DB_SCHEMA(title: str | None = None, check: bool = False):
    '''notion objects - DB와 페이지의 property가 통일되도록 함수 사용'''
    def builder(titleObj, checkboxObj):
        return {
            'title': {
                'id': 'title',
                'type': 'title',
                'title': titleObj
            },
            'Empty Text': {
                'id': 'Empty Text',
                "type": "checkbox",
                "checkbox": checkboxObj
            }
        }

    if title == None:
        db_properties = builder(
            titleObj={},
            checkboxObj={}
        )
        db_properties['title']['name'] = '제목'
        db_properties['Empty Text']['name'] = 'Empty Text'
        return db_properties
    else:
        page_values = builder(
            titleObj=[
                rich_text(title)
            ],
            checkboxObj=check
        )
        return page_values
# endregion


async def blocks_of_page_shallow(page_id: str = ROOT_PAGE):
    '''애플 메모 페이지의 block children'''
    block_list = []

    start_cursor: str | None = None
    # pagination에 사용
    while True:
        # page_id가 가지고 있는 block 요청
        response = DotMap(await notion.blocks.children.list(
            block_id=page_id,
            start_cursor=start_cursor,
        ))
        block_list.extend(response.results)

        # pagination 다음 요청하기
        if response.has_more:
            start_cursor = response.next_cursor if response.next_cursor else None
        else:
            break
    return block_list


async def original_folders():
    '''노션 페이지의 기존 DB 탐색'''
    folders_id: dict[str, str] = {}

    block_list = await blocks_of_page_shallow()
    for block in filter(lambda block: block.type == 'child_database', block_list):
        folders_id[block.child_database.title] = block.id
    return folders_id


async def create_folder(title: str) -> str:
    '''폴더 DB 생성 -> id 반환'''
    response = DotMap(await notion.databases.create(
        parent=parent(ROOT_PAGE, is_page=True),
        title=[
            rich_text(title)
        ],
        properties=DB_SCHEMA()
    ))
    return response.id


def page_contents(raw_text: str):
    '''
    길이가 짧은 경우, 텍스트를 담은 하나의 block을 반환한다.
    길이가 긴 경우, 텍스트를 최대한 여러 block으로 쪼갠다.
    blocks의 개수가 너무 많아지면, 여러 개의 chunk로 나눈다.
    '''

    MAX_LEN = 2000
    MAX_BLOCK = 100

    result: list[dict] = []
    if len(raw_text) > MAX_LEN:
        for small_text in raw_text.split('\n\n'):
            if len(small_text) > MAX_LEN:
                for tiny_text in small_text.split('\n'):
                    if len(tiny_text) > MAX_LEN:
                        raise Exception({
                            'message': 'tiny_text is still too big',
                            'length': len(tiny_text),
                            'tiny_text': tiny_text
                        })
                    else:
                        result.append(block(tiny_text))
            else:
                result.append(block(small_text))
                result.append(block(''))
    else:
        result.append(block(raw_text))

    def chunks(lst, n):
        """Yield successive n-sized chunks from lst."""
        return [lst[i:i + n] for i in range(0, len(lst), n)]
    return chunks(result, MAX_BLOCK)


# add_note에서 ERROR의 번호를 'Log n'으로 나타낸다. 5개의 에러가 발생하면 프로그램이 종료된다.
log_count = 0


async def add_note(folder_id: str, properties: dict, page_text: str):
    '''폴더 DB에 note 추가'''

    try:
        page_obj = DotMap(await notion.pages.create(
            parent=parent(folder_id),
            properties=properties
        ))
        for blocks in page_contents(page_text):
            await notion.blocks.children.append(
                block_id=page_obj.id,
                children=blocks,
            )
    except Exception as e:
        global log_count
        pprint(f'Log {log_count}')
        log_count += 1
        if log_count >= 5:
            exit()

        pprint((folder_id, properties))
        # pprint(page_contents(page_text))
        pprint(e)


async def main():
    success_list, fail_list = readFile_forced()
    # folders_id[title] = id
    folders_id = await original_folders()

    # 각 note에 대해서
    # 1) folder가 없으면 만들고
    # 2) folder에 note 추가
    start = time.time()
    async with asyncio.TaskGroup() as tg:
        for success_note in success_list:
            if success_note.folder not in folders_id:
                new_id = await create_folder(success_note.folder)
                folders_id[success_note.folder] = new_id

            # await하지 않기
            tg.create_task(add_note(folder_id=folders_id[success_note.folder],
                                    properties=DB_SCHEMA(success_note.title),
                                    page_text=success_note.plaintext.removeprefix(success_note.title).strip()))

        pprint(f'{len(fail_list)}개의 Failed Notes')
        for fail_note in fail_list:
            if fail_note.folder not in folders_id:
                new_id = await create_folder(fail_note.folder)
                folders_id[fail_note.folder] = new_id

            pprint((fail_note.folder, fail_note.title))
            # await하지 않기
            tg.create_task(add_note(folder_id=folders_id[fail_note.folder],
                                    properties=DB_SCHEMA(
                                        fail_note.title, check=True),
                                    page_text=''))
    end = time.time()
    pprint(f'Adding notes finished. {end - start}s elapsed')

    # 각 folder에 대해서
    # 1) 총 몇 개 있는지 세주기
    # 2) emptyText가 몇 개 있는지 세주기
    for folder_title in sorted(folders_id):
        folder_id = folders_id[folder_title]

        page_list = DotMap((await notion.databases.query(folder_id))).results
        checkedLen = len(list(
            filter(lambda page: page.properties['Empty Text'].checkbox, page_list)))

        pprint(f'{folder_title}: 총 {len(page_list)}개, check {checkedLen}개')


asyncio.run(main())
