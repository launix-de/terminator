BIN := terminator2
TARGET := target/release/$(BIN)

.PHONY: all release debug run clean

all: $(BIN)

$(BIN): release
	@cp $(TARGET) $(BIN)

release:
	@cargo build --release

debug:
	@cargo build

run:
	@cargo run

clean:
	@cargo clean
	@rm -f $(BIN)
