This utility is a "random-access FIFO". It has three interfaces:
- **Push onto queue:**
    - `wr_push_i` and `wr_data_i`
    - When `wr_push_i` is asserted, `wr_data_i` will be pushed onto the FIFO if there is space
- **Pop off of queue**
    - `rd_head_data_o` is always valid unless the queue is empty
    - `rd_pop_i` will pop an entry and cause `rd_head_data_o` to update
- **Read random entries**
    - `rd_req_i`, `rd_gnt_o`, `rd_addr_i`, `rd_data_o`, `rd_err_o`
    - Signals behave consistently with `mem_if_utils`
    - `rd_err_o` will be asserted after attempting to read an invalid entry in the queue
    - Addresses are relative i.e. address 0 always points to the oldest queue item. This mean the same address may read different data if a pop has occurred.

In addition there are status signals:
- `full_o` is asserted when the queue is full
- `almost_full_o` is asserted when the remaining queue spaces are lower than or equal to parameter `AlmostFullThreshold`
- `n_buffered_o` is the number of items currently on the queue
- `empty_o` is asserted when the queue is empty

The data type in the queue is passed in as a parameter allowing you to store structs, large vectors, or any other data type as queue items.

The internal storage of the FIFO is implemented as a two dimensional packed array:
```verilog
dtype_t [Depth-1:0] fifo_storage;
```
Your synthesis tool may infer this as memory or as flops. Note that it requires two simultaneous read paths.