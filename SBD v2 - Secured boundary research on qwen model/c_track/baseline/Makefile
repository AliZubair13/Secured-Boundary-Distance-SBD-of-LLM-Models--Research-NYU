CC = gcc
CFLAGS = -fsanitize=address,undefined -g -Wall
TARGET = test_basic

all:
$(CC) $(CFLAGS) -o $(TARGET) tests/test_basic.c logfmt.c

clean:
rm -f $(TARGET)
