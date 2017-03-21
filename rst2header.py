from io import StringIO
import re


class RegBit(object):
    rst_1bit = '   * - {}\n     - {}\n     - {}\n     - {}\n     - {}\n'
    rst_bits = '   * - {}:{}\n     - {}\n     - {}\n     - {}\n     - {}\n'
    to_str = ('bits: {}:{}\nname: {}\ndescription: {}\n'
              'access: {}\nreset: {}\ntype: {}\n')
    des_pattern = re.compile('^reserved')

    def __init__(self, up, down, name, description, access, reset, val_type):
        if RegBit.des_pattern.match(description.lower()) and name != '--':
            raise Exception('{} is not match description'.format(name))
        self.up, self.down = up, down
        self.name, self.description = name, description
        self.access, self.reset, self.type = access, reset, val_type

    def generate_rst(self):
        name_des = ('**{}** {}'.format(self.name, self.description)
                    if self.name == '--' else self.description)
        if self.up == self.down:
            return RegBit.rst_1bit.format(self.up, name_des, self.access,
                                          self.reset, self.type)
        else:
            return RegBit.rst_bits.format(self.up, self.down, name_des,
                                          self.access, self.reset, self.type)

    def __str__(self):
        return RegBit.to_str.format(self.up, self.down, self.name,
                                    self.description, self.access, self.reset,
                                    self.type)


class IspReg(object):
    def __init__(self, name: str, description: str, offset: int):
        self.name = name.lower()
        self.description = description
        self.offset = offset
        self.des_name = '{} ({}, 0x{:04X})'.format(name.upper(),
                                                   description, offset)
        self.bits = []

    def append(self, bits: RegBit):
        self.bits.append(bits)

    def check_bits(self):
        if self.bits[0].down:
            raise Exception('{} is not begin with 0'.format(self.des_name))
        last_up = -1
        for bit in self.bits:
            if bit.down != last_up + 1:
                raise Exception('bit conflict at {} {}:{}'.
                                format(self.des_name, bit.up, bit.down))
            if bit.up < bit.down:
                raise Exception('bit conflict at {} {}:{}'.
                                format(self.des_name, bit.up, bit.down))
            last_up = bit.up
        if last_up != 31:
            raise Exception('{} is not end with 31'.format(self.des_name))

    def generate_header(self, cut_header=True):
        self.bits.sort(key=lambda b: b.down)
        self.check_bits()
        name = '_'.join(self.name.split('_')[1:]) if cut_header else self.name
        header = StringIO()
        header.write('\tunion {\n')
        header.write('\t\tuint32_t {};\n'.format(name))
        header.write('\t\tstruct {\n')
        reserved_index = 0
        for bit in self.bits:
            bit_num = bit.up - bit.down + 1
            if bit.name == '--':
                header.write('\t\t\treserved{}:{};\n'.
                             format(reserved_index, bit_num))
                reserved_index += 1
            else:
                header.write('\t\t\t{}:{};\n'.format(bit.name, bit_num))
        header.write('\t\t}} {}_bit;\n'.format(name))
        header.write('\t};\n')
        return header.getvalue()


class IspModule(object):
    name_pattern = re.compile(r'^([A-Z][A-Z0-9_]+) ?\((.+?), ?'
                              r'([0-9A-Fa-f]{4})[hH]\)$')
    section_pattern = re.compile(r'^(\^+)$')
    bit_pattern = re.compile(r'^ {3}\* - (\d+)(?::(\d+))?$')
    reserved_pattern = re.compile(r'^ {5}- reserved.?$')
    des_pattern = re.compile(r'^ {5}- \*\*(\w+?)(?:\[(\d+)\])?')
    access_pattern = ['RW', 'R/W', 'R', 'W1P', 'W1C', 'W1P/R']
    reset_pattern = re.compile(r'^0x[0-9A-Fa-f]+$')
    type_pattern = ['U', 'S']

    def __init__(self, rst_file: str):
        with open(rst_file, 'r') as rf:
            rst_lines = rf.readlines()
        for line in rst_lines:
            name_match = IspModule.name_pattern.match(line)
            if name_match:
                print(name_match.groups())


if __name__ == '__main__':
    isp_module = IspModule('blc.rst')
