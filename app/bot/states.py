"""FSM-состояния диалога."""

from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    # Ожидание идентификатора после неуспешного поиска (в первую очередь телефон).
    waiting_identifier = State()
    # Режим правки текущей карточки после кнопки «Обновить».
    updating_card = State()
    # Ожидание решения по дублю телефона (объединить/раздельно).
    resolving_duplicate = State()
    # Онбординг агента при первой встрече: сначала ФИО, затем телефон.
    onboarding_name = State()
    onboarding_phone = State()
    # Диалоговое доуточнение недостающего обязательного поля черновика.
    collecting_field = State()
    # Ожидание нажатия кнопки «Внести данные» после превью.
    confirming_save = State()
