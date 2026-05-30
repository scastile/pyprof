"""Sample script that produces interesting profiling data for pyprof screenshots."""

import time
import math
import random
import hashlib


def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


def sieve_of_eratosthenes(limit):
    is_prime = [True] * (limit + 1)
    is_prime[0] = is_prime[1] = False
    for i in range(2, int(limit**0.5) + 1):
        if is_prime[i]:
            for j in range(i * i, limit + 1, i):
                is_prime[j] = False
    return [i for i, prime in enumerate(is_prime) if prime]


def matrix_multiply(a, b):
    n = len(a)
    result = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            for k in range(n):
                result[i][j] += a[i][k] * b[k][j]
    return result


def stress_hash(iterations):
    data = "benchmark"
    for _ in range(iterations):
        data = hashlib.sha256(data.encode()).hexdigest()
    return data


def recursive_quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return recursive_quicksort(left) + middle + recursive_quicksort(right)


def simulate_io():
    for _ in range(5):
        time.sleep(0.05)


def main():
    # CPU-bound: recursive fibonacci
    for i in range(25, 32):
        fibonacci(i)

    # CPU-bound: prime sieve
    sieve_of_eratosthenes(50000)

    # CPU-bound: matrix multiplication
    size = 64
    a = [[random.random() for _ in range(size)] for _ in range(size)]
    b = [[random.random() for _ in range(size)] for _ in range(size)]
    matrix_multiply(a, b)

    # CPU-bound: hashing
    stress_hash(50000)

    # CPU-bound: sorting
    data = [random.randint(0, 100000) for _ in range(50000)]
    recursive_quicksort(data)

    # IO-bound simulation
    simulate_io()

    # More math
    for _ in range(100000):
        math.sqrt(random.random())


if __name__ == "__main__":
    main()
