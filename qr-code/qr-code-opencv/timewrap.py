import time
# если нет логгера, можно заменить на print

def timewrap(function):
    """
    Декоратор для измерения времени работы функции
    """
    def wrapper(*args, **kwargs):
        t0 = time.time()
        res = function(*args, **kwargs)
        d = time.time() - t0
        print(f'Функция {function.__name__} заняла времени: {d:.3f} сек')
        return res
    return wrapper
