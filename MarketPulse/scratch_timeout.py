import concurrent.futures
import time

def run():
    print("agent run started")
    time.sleep(300)
    print("agent run finished")

executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
future = executor.submit(run)

start_time = time.time()
timeout = 5
while True:
    try:
        res = future.result(timeout=0.5)
        print("Success:", res)
        break
    except concurrent.futures.TimeoutError:
        if time.time() - start_time > timeout:
            print("Timed out!")
            future.cancel()
            break
