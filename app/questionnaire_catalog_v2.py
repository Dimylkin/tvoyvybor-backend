"""Immutable catalogue for the second version of the interest questionnaire.

Signals are context-specific, not scores. An option can support several traits;
all contributions from one question are deduplicated during interpretation.
"""

_BIPOLAR = [
    (
        "Учебная игра по физике",
        "Придумать механику и правила игры",
        "creation",
        "Подготовить материалы и распределить роли",
        "organization",
    ),
    (
        "Сайт университетского события",
        "Описать условия регистрации и количество мест",
        "B systems",
        "Сделать форму понятной новичку",
        "F interfaces improvement",
    ),
    (
        "Очереди в столовой",
        "Сравнить время ожидания и длину очередей",
        "D data analysis",
        "Расспросить студентов и сотрудников",
        "R people needs",
    ),
    (
        "Программа иногда сбоит",
        "Выяснить причину известного сбоя и исправить её",
        "investigation fixing",
        "Проверить программу в разных условиях",
        "testing software",
    ),
    (
        "Каталог кружков",
        "Доработать поиск и фильтры на экране",
        "F interfaces improvement",
        "Собрать правило отбора записей для поиска",
        "B code creation",
    ),
    (
        "Незнакомое задание на практике",
        "Изучить примеры и самостоятельно подготовить решение",
        "independent",
        "Собрать идеи коллег и обсудить решение",
        "collaboration",
    ),
    (
        "Подготовка выставки",
        "Связать этапы и составить план",
        "planning",
        "Испытать две схемы на небольшом участке",
        "experiment",
    ),
    (
        "Итоги исследования для студентов",
        "Найти закономерность в исходных данных",
        "D data analysis",
        "Наглядно объяснить готовые выводы",
        "visualization",
    ),
    (
        "Учёт оборудования",
        "Написать проверку правил выдачи",
        "B code creation",
        "Уточнить исключения у сотрудников и описать условия",
        "R people requirements",
    ),
    (
        "Запись в студенческую студию",
        "Выяснить у организаторов, кому и когда нужна запись",
        "R people needs requirements",
        "Перестроить экран выбора времени",
        "F interfaces improvement",
    ),
    (
        "Сервис расписания",
        "Поправить отображение расписания на телефоне",
        "F interfaces improvement",
        "Сравнить данные о посещениях и найти закономерность",
        "D data analysis",
    ),
    (
        "Черновик учебного проекта",
        "Сделать два прототипа и сравнить их",
        "experiment",
        "Описать связи компонентов и порядок работ",
        "planning systems",
    ),
    (
        "Отзыв на проект",
        "Обсудить отзыв с командой и вместе выбрать правку",
        "collaboration feedback",
        "Самостоятельно воспроизвести замечание и подготовить правку",
        "independent feedback",
    ),
    (
        "Городская библиотека меняет расписание",
        "Собрать потребности читателей и согласовать условия",
        "R people requirements",
        "Сопоставить посещения по дням",
        "D data analysis",
    ),
]

_CHOICE = [
    (
        "Посетители бросают запись на мероприятие",
        1,
        [
            ("rules", "Проверить правила приёма заявок", "B systems investigation"),
            ("screen", "Упростить экран", "F interfaces improvement"),
            ("data", "Сравнить данные по этапам записи", "D data analysis"),
            (
                "requirements",
                "Уточнить требования организаторов и посетителей",
                "R people requirements",
            ),
        ],
    ),
    (
        "Демонстрация учебного проекта",
        2,
        [
            ("create", "Создать новую возможность", "creation"),
            ("improve", "Улучшить существующий сценарий", "improvement"),
            ("test", "Проверить пограничные случаи", "testing software"),
            ("organize", "Упорядочить материалы к показу", "structuring"),
        ],
    ),
    (
        "Сервис выдачи пропусков готовится к запуску",
        1,
        [
            ("code", "Изменить код проверки пропуска", "B code fixing"),
            ("screen", "Упростить экран гостя", "F interfaces improvement"),
            ("data", "Изучить данные по отказам", "D data investigation"),
            (
                "requirements",
                "Описать исключения по разговору с охраной",
                "R people requirements",
            ),
        ],
    ),
    (
        "Задача в команде с расплывчатым началом",
        1,
        [
            ("example", "Разобрать пример самому", "independent"),
            ("discuss", "Обсудить варианты с коллегой", "collaboration"),
            ("draft", "Испытать черновик", "experiment"),
            ("plan", "Составить последовательность шагов", "planning"),
        ],
    ),
    (
        "Подготовка системы бронирования к сдаче",
        2,
        [
            ("test", "Проверить её в разных условиях", "testing software"),
            ("diagnose", "Найти причину одного известного сбоя", "investigation"),
            ("group", "Сгруппировать замечания", "structuring"),
            ("observe", "Выяснить, где посетители застревают", "user_research"),
        ],
    ),
    (
        "Навигация на сайте вуза",
        2,
        [
            ("observe", "Понаблюдать, как студент ищет нужный раздел", "user_research"),
            ("menu", "Перестроить меню", "F interfaces improvement"),
            ("agree", "Согласовать с факультетами состав разделов", "R requirements"),
            (
                "test",
                "Проверить переходы на нескольких устройствах",
                "F interfaces testing software",
            ),
        ],
    ),
]

_SCALE = [
    (
        "Выдача книг",
        "Написать небольшую программу, проверяющую условия выдачи",
        "B code systems",
    ),
    (
        "Запись на тренировку",
        "Переделать экран записи и проверить его удобство",
        "F interfaces improvement",
    ),
    (
        "Университетское исследование",
        "Найти объяснения необычных значений в таблице",
        "D data analysis",
    ),
    (
        "Встреча со студенческим клубом",
        "Провести короткое интервью и составить требования к сервису",
        "R people requirements",
    ),
]

QUESTIONS_V2 = (
    [
        {
            "id": f"V2Q{i:02}",
            "format": "bipolar",
            "context": context,
            "text": "Что тебе ближе в этой ситуации?",
            "alternatives": [
                {"id": "left", "label": left, "signals": left_signals.split()},
                {"id": "right", "label": right, "signals": right_signals.split()},
            ],
        }
        for i, (context, left, left_signals, right, right_signals) in enumerate(
            _BIPOLAR, 1
        )
    ]
    + [
        {
            "id": f"V2Q{i:02}",
            "format": "choice",
            "context": context,
            "text": "Что тебе интереснее сделать?",
            "max_choices": maximum,
            "options": [
                {"id": key, "label": label, "signals": signals.split()}
                for key, label, signals in options
            ],
        }
        for i, (context, maximum, options) in enumerate(_CHOICE, 15)
    ]
    + [
        {
            "id": f"V2Q{i:02}",
            "format": "scale",
            "context": context,
            "text": text,
            "prompt": "Насколько тебе было бы интересно этим заняться?",
            "signals": signals.split(),
        }
        for i, (context, text, signals) in enumerate(_SCALE, 21)
    ]
)
