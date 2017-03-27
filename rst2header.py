import os
import re
import sys
from io import StringIO

reserved_str = '--'


class RegField(object):
    rst_1bit = '   * - {}\n     - {}\n     - {}\n     - {}\n     - {}\n'
    rst_bits = '   * - {}:{}\n     - {}\n     - {}\n     - {}\n     - {}\n'
    to_str = ('bits: {}:{}\nname: {}\ndescription: {}\n'
              'access: {}\nreset: {}\ntype: {}\n')

    def __init__(self, bit, name, description, access, reset, val_type):
        self.up, self.down = bit
        self.name, self.description = name, description
        self.access, self.reset, self.type = access, reset, val_type

    def __str__(self):
        name_des = ('**{}** {}'.format(self.name, self.description)
                    if self.name != reserved_str else self.description)
        name_des = re.sub('\n(?!$)', '\n\n       ', name_des)
        if self.up == self.down:
            return RegField.rst_1bit.format(self.up, name_des, self.access,
                                            self.reset, self.type)
        else:
            return RegField.rst_bits.format(self.up, self.down, name_des,
                                            self.access, self.reset, self.type)


class Register(object):
    header_str = ('.. list-table::\n'
                  '   :header-rows: 1\n\n'
                  '   * - Bits\n'
                  '     - Description\n'
                  '     - Access\n'
                  '     - Reset\n'
                  '     - Value\n')
    long_table_header_str = ('.. list-table::\n'
                             '   :header-rows: 1\n'
                             '   :class: longtable\n\n'
                             '   * - Bits\n'
                             '     - Description\n'
                             '     - Access\n'
                             '     - Reset\n'
                             '     - Value\n')

    def __init__(self, name, description, offset):
        self.name = name.lower()
        self.description, self.description_ex = description
        self.offset = offset
        self.description_end = ''
        self.is_long_table = False
        if self.description_ex:
            self.full_des = ('{} ({}, 0x{:04X}_{:04X}) {}'.
                             format(name.upper(), description[0],
                                    offset >> 16, offset & 0xffff,
                                    description[1]))
        else:
            self.full_des = ('{} ({}, 0x{:04X}_{:04X})'.
                             format(name.upper(), description[0],
                                    offset >> 16, offset & 0xffff))
        self.reg_fields = []

    def __str__(self):
        reg_str = StringIO()
        reg_str.write('{}\n'.format(self.full_des))
        reg_str.write('^' * len(self.full_des) + '\n')
        if self.is_long_table:
            reg_str.write(Register.long_table_header_str)
        else:
            reg_str.write(Register.header_str)
        for reg_field in reversed(self.reg_fields):
            reg_str.write(str(reg_field))
        reg_str.write('\n')
        if self.description_end:
            reg_str.write('{}'.format(self.description_end.
                                      replace('\n', '\n\n')))
            reg_str.write('\n\n')
        return reg_str.getvalue()

    def set_all_bits(self, reg_fields):
        for reg_field in reg_fields:
            self.reg_fields.append(reg_field)
        self.check_bits()

    def check_bits(self):
        self.reg_fields.sort(key=lambda b: b.down)
        cmp_down = 0
        for reg_field in self.reg_fields:
            if reg_field.down != cmp_down:
                if reg_field.down == reg_field.up:
                    raise Exception('bit collide or error at {} bit {}'.
                                    format(self.full_des, reg_field.up))
                else:
                    raise Exception('bit collide or error at {} bit {}:{}'.
                                    format(self.full_des, reg_field.up,
                                           reg_field.down))
            if reg_field.up < reg_field.down:
                raise Exception('bit conflict or error at {} bit {}:{}'.
                                format(self.full_des, reg_field.up,
                                       reg_field.down))
            cmp_down = reg_field.up + 1
        if cmp_down != 32:
            raise Exception('{} is not begin with bit 31'.format(self.full_des))

    def get_isp_reg(self):
        self.check_bits()
        return self

    def generate_header(self, cut_prefix=''):
        self.check_bits()
        name = '_'.join(self.name.split('_')[1:]) if cut_prefix else self.name
        header = StringIO()
        header.write('\tunion {\n')
        header.write('\t\tuint32_t {};\n'.format(name))
        header.write('\t\tstruct {\n')
        reserved_index = 0
        for reg_field in self.reg_fields:
            bit_num = reg_field.up - reg_field.down + 1
            if reg_field.name == reserved_str:
                header.write('\t\t\treserved{}:{};\n'.
                             format(reserved_index, bit_num))
                reserved_index += 1
            else:
                header.write('\t\t\t{}:{};\n'.format(reg_field.name, bit_num))
        header.write('\t\t}} {}_bit;\n'.format(name))
        header.write('\t};\n')
        return header.getvalue()


class Module(object):
    start_str = ('.. raw:: latex\n\n'
                 '   \setregistertablestyle\n\n'
                 '.. tabularcolumns:: '
                 '|K{1cm}|p{10cm}|K{1.2cm}|K{1cm}|K{1cm}|\n\n')
    end_str = '.. tabularcolumns:: |l|l|l|l|l|l|l|l|l|l|\n'

    def __init__(self, name):
        self.name = name
        self.regs = []

    def __str__(self):
        module_str = StringIO()
        module_str.write(Module.start_str)
        for reg in self.regs:
            module_str.write(str(reg))
        module_str.write(Module.end_str)
        return module_str.getvalue()

    def append_regs(self, regs):
        self.regs.extend(regs)
        for i, reg in enumerate(self.regs):
            pre_reg = self.regs[i - 1] if i else None
            if reg.offset % 4 or (pre_reg and reg.offset < pre_reg.offset):
                raise Exception('reg offset is error at {} to {}'.
                                format(reg.offset, pre_reg.offset))

    def get_module_prefix(self):
        prefix = ''
        for reg in self.regs:
            if prefix:
                if prefix != reg.name.split('_')[0]:
                    prefix = ''
                    break
            else:
                prefix = reg.name.split('_')[0]
        return prefix

    def generate_user_headers(self, file_handler, cut_prefix=False):
        file_handler.write('#include <stdint.h>\n\n')
        for reg in self.regs:
            file_handler.write('#define {} 0x{:08X}\n'.
                               format(reg.name.upper(), reg.offset))
        file_handler.write('\nstruct {}_reg {{\n'.format(self.name))
        cmp_offset = reserved_index = 0
        for reg in self.regs:
            if reg.offset != cmp_offset:
                file_handler.write('\tuint32_t reserved{}[{}];\n'.
                                   format(reserved_index,
                                          (reg.offset - cmp_offset) // 4))
                reserved_index += 1
            cmp_offset = reg.offset + 4
            file_handler.write(reg.generate_header(cut_prefix))
        file_handler.write('};\n')

    def generate_kernel_headers(self, file_handler):
        for reg in self.regs:
            file_handler.write('#define {} 0x{:04X}\n'.
                               format(reg.name.upper(), reg.offset))

    def generate_headers(self, file, user_space=True):
        with open(file, 'w') as file_handler:
            file_handler.write('#ifdef _{}_REG_H\n'.format(self.name.upper()))
            file_handler.write('#define _{}_REG_H\n\n'.
                               format(self.name.upper()))
            if user_space:
                cut_prefix = True if self.get_module_prefix() else False
                self.generate_user_headers(file_handler, cut_prefix=cut_prefix)
            else:
                self.generate_kernel_headers(file_handler)
            file_handler.write('\n#endif /* _{}_REG_H */\n'.
                               format(self.name.upper()))


class RstParser(object):
    name_pattern = re.compile(r'^([A-Z][A-Z0-9_]+) \((.+?), '
                              r'0x([0-9A-F]{4}_[0-9A-F]{4})\)(?: (.+?))?$')
    section_pattern = re.compile(r'^(\^+)$')
    bit_pattern = re.compile(r'^ {3}\* - (\d+)(?::(\d+))?$')
    reserved_pattern = '     - Reserved'
    des0_pattern = re.compile(r'^ {5}- \*\*(\S+?)\*\* (.*)$')
    des1_pattern = re.compile(r'^ {7}(.+)$')
    access_pattern = re.compile(r'^ {5}- (R/W|R|W1P|W1C|W1P/R|' +
                                reserved_str + r')$')
    reset_pattern = re.compile(r'^ {5}- (0x[0-9A-F]+|' + reserved_str +
                               r')$')
    type_pattern = re.compile(r'^ {5}- (U|S|' + reserved_str + ')$')
    space_pattern = re.compile(r'[ \t]+$')

    def __init__(self, rst_file):
        self.file = rst_file
        self.i = self.end = 0
        self.start_file_line = 7
        self.regs = []
        with open(rst_file, 'r') as rf:
            self.rst_lines = rf.readlines()
        self.strip_rst_lines()
        self.set_parse_area()
        self.parse_rst_lines()

    def goto_next_line(self):
        self.i += 1

    def goto_next_n_lines(self, n):
        self.i += n

    @property
    def file_line(self):
        return self.i + self.start_file_line

    @property
    def cur_line(self):
        return self.rst_lines[self.i]

    @property
    def pre_line(self):
        return self.rst_lines[self.i - 1]

    @property
    def next_line(self):
        return self.rst_lines[self.i + 1]

    def strip_rst_lines(self):
        for i, line in enumerate(self.rst_lines):
            if RstParser.space_pattern.search(line):
                raise Exception('{}: {} - {}: has trailing white space'.
                                format(self.file, i + 1, repr(line)))
            if line.find('\t') >= 0:
                raise Exception('{}: {} - {}: can not use tab for indenting'.
                                format(self.file, i + 1, repr(line)))
            if line == '\n' and not self.rst_lines[i - 1]:
                raise Exception('{}: {} - {}: do not use two continuous blank'
                                'line'.format(self.file, i, repr(line)))
            self.rst_lines[i] = line.rstrip()

    def set_parse_area(self):
        if ('\n'.join(self.rst_lines[0:self.start_file_line - 1]) + '\n' !=
                Module.start_str):
            raise Exception('{}: rst file must start with:\n{}'.
                            format(self.file, Module.start_str))
        end = -1
        while not self.rst_lines[end]:
            end -= 1
        if self.rst_lines[end] + '\n' != Module.end_str:
            raise Exception('{}: rst file must end with:\n{}'.
                            format(self.file, Module.end_str))
        # noinspection PyAttributeOutsideInit
        self.rst_lines = self.rst_lines[6:end]
        self.end = len(self.rst_lines)

    def parse_rst_lines(self):
        i = 6
        cmp_offset = 0
        while i < self.end:
            reg = self.get_next_reg()
            if not reg:
                break
            if reg.offset < cmp_offset or reg.offset % 4:
                raise Exception('{}> {}\n'.format(self.file, reg.full_des))
            cmp_offset = reg.offset + 4
            self.regs.append(reg)

    def get_next_reg(self):
        try:
            name, description, offset = self.cur_pos_to_reg_attr()
        except IndexError:
            return None
        reg = Register(name, description, offset)
        if ('\n'.join(self.rst_lines[self.i:self.i + 8]) + '\n' ==
                Register.header_str):
            self.goto_next_n_lines(8)
        elif ('\n'.join(self.rst_lines[self.i:self.i + 9]) + '\n' ==
                Register.long_table_header_str):
            reg.is_long_table = True
            self.goto_next_n_lines(9)
        else:
            raise Exception('{}: {}> table header string error\n'.
                            format(self.file, self.file_line))
        self.append_all_reg_field(reg)
        return reg

    def append_all_reg_field(self, reg):
        bits = []
        while True:
            bit = self.cur_line_to_reg_field()
            bits.append(bit)
            if not bit.down:
                self.goto_next_line()
                reg.description_end = self.get_register_end_description()
                break
        reg.set_all_bits(bits)

    def get_register_end_description(self):
        result = StringIO()
        while self.i < self.end and not self.try_cur_pos_to_reg_attr()[0]:
            if self.cur_line:
                if not self.pre_line:
                    result.write('\n')
                else:
                    result.write(' ')
                result.write(self.cur_line)
            self.goto_next_line()
        return result.getvalue().lstrip()

    def cur_line_to_reg_field(self):
        bit = self.cur_line_to_reg_bit()
        name, description = self.cur_pos_to_name_description()
        access = self.cur_line_to_reg_access()
        reset = self.cur_line_to_reg_reset()
        val_type = self.cur_line_to_reg_type()
        if name == reserved_str:
            reg_field = RegField(bit, reserved_str, 'Reserved', reserved_str,
                                 reserved_str, reserved_str)
        else:
            reg_field = RegField(bit, name, description, access, reset,
                                 val_type)
        return reg_field

    def cur_line_to_reg_access(self):
        access_match = RstParser.access_pattern.match(self.cur_line)
        if not access_match:
            raise Exception('{}: {}> {} can not find any access flag\n'
                            'correct flag is \'R/W|R|W1P|W1C|W1P/R|--\'\n'.
                            format(self.file, self.file_line,
                                   repr(self.cur_line)))
        self.goto_next_line()
        return access_match.group(1)

    def cur_line_to_reg_reset(self):
        reset_match = RstParser.reset_pattern.match(self.cur_line)
        if not reset_match:
            raise Exception('{}: {}> {} reset value is error\n'
                            'correct eg: 0xA4. must be upper case\n'.
                            format(self.file, self.i + 1, self.cur_line))
        reset = reset_match.group(1)
        reset = ('0x{:X}'.format(int(reset, 16)) if reset != reserved_str
                 else reset)
        self.goto_next_line()
        return reset

    def cur_line_to_reg_type(self):
        type_match = RstParser.type_pattern.match(self.cur_line)
        if not type_match:
            raise Exception('{} {}> {} type flag incorrect\n'
                            'correct is \'U|S|--\''.
                            format(self.file, self.i + 1, self.cur_line))
        self.goto_next_line()
        return type_match.group(1)

    def cur_pos_to_name_description(self):
        if self.description_is_reserved():
            self.goto_next_line()
            return reserved_str, 'Reserved'
        return self.get_description()

    def description_is_reserved(self):
        if self.cur_line == RstParser.reserved_pattern:
            return True
        else:
            return False

    def get_description(self):
        des0_match = RstParser.des0_pattern.match(self.cur_line)
        if des0_match:
            name = des0_match.group(1)
            description = des0_match.group(2)
            self.goto_next_line()
            while self.i < self.end:
                des1_match = RstParser.des1_pattern.match(self.cur_line)
                if des1_match:
                    if not self.pre_line:
                        description += '\n' + des1_match.group(1)
                    else:
                        description += ' ' + des1_match.group(1)
                    self.goto_next_line()
                elif not self.cur_line:
                    self.goto_next_line()
                else:
                    break
            return name, description
        else:
            raise Exception('{}: {}> {}: description format is error\n'
                            'correct string is \'Reserved\' or '
                            '\'**signal** description\'\n'.
                            format(self.file, self.file_line,
                                   repr(self.cur_line)))

    def cur_line_to_reg_bit(self):
        bit_match = RstParser.bit_pattern.match(self.cur_line)
        if bit_match:
            self.goto_next_line()
            up = bit_match.group(1)
            down = bit_match.group(2) if bit_match.group(2) else up
            return int(up), int(down)
        else:
            raise Exception('{}: {}> {} bit format error or bit is not end'
                            'with 0'.format(self.file, self.file_line,
                                            repr(self.cur_line)))

    def cur_pos_to_reg_attr(self):
        name, description, offset = self.try_cur_pos_to_reg_attr()
        if name:
            self.goto_next_n_lines(2)
            return name, description, offset
        else:
            raise Exception('{}: {}> {}can not find reg name'.
                            format(self.file, self.file_line, self.cur_line))

    def raise_reg_name_error(self):
        raise Exception('{}: {}> {}: register name format error\n'
                        'notice whitespace needed and the length of \'^\',\n'
                        'correct is\n'
                        'NAME (des, 0xXXXX_XXXX) des_ex\n'
                        '^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'.
                        format(self.file, self.file_line,
                               self.cur_line))

    def try_cur_pos_to_reg_attr(self):
        i = self.i
        name_match = RstParser.name_pattern.match(self.rst_lines[i])
        i += 1
        if name_match:
            section_match = RstParser.section_pattern.match(self.rst_lines[i])
            if (section_match and len(name_match.group(0)) <= len(
                    section_match.group(0))):
                name = name_match.group(1)
                offset = name_match.group(3)
                description = name_match.group(2), name_match.group(4)
                return name, description, int(offset.replace('_', ''), 16)
            else:
                self.raise_reg_name_error()
        elif RstParser.section_pattern.match(self.rst_lines[i]):
            self.raise_reg_name_error()
        return '', ['', None], 0

    def get_all_regs(self):
        return self.regs


def generate_header_files(modules_dir, headers_dir):
    modules = [name for name in os.listdir(modules_dir)
               if os.path.isdir(os.path.join(modules_dir, name))]
    if not os.path.exists(headers_dir):
        os.makedirs(headers_dir)
    user_dir = os.path.join(headers_dir, 'user')
    kernel_dir = os.path.join(headers_dir, 'kernel')
    if not os.path.exists(user_dir):
        os.mkdir(user_dir)
    if not os.path.exists(kernel_dir):
        os.mkdir(kernel_dir)
    for mod in modules:
        input_file = os.path.join(modules_dir, mod, 'registers.rst')
        user_file = os.path.join(user_dir, '{}_reg.h'.format(mod))
        kernel_file = os.path.join(kernel_dir, '{}_reg.h'.format(mod))
        print('convert {} to {}'.format(input_file, user_file))
        rst_parser = RstParser(input_file)
        isp_module = Module(mod)
        isp_module.append_regs(rst_parser.get_all_regs())
        isp_module.generate_headers(user_file)
        print('convert {} to {}'.format(input_file, kernel_file))
        isp_module.generate_headers(kernel_file, user_space=False)


def merge_header_files(headers_dir):
    with open(os.path.join(headers_dir, 'isp_reg.h'), 'w') as isp_header_file:
        modules = [name for name in os.listdir(headers_dir)
                   if name.endswith('.h') and name != 'isp_reg.h']
        for mod in modules:
            isp_header_file.write('#include "{}"\n'.format(mod))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: {} modules_dir headers_dir'.format(sys.argv[0]))
        exit(1)
    print('=' * 80)
    print('Begin convert rst files to C header files')
    generate_header_files(*sys.argv[1:])
    merge_header_files(os.path.join(sys.argv[2], 'user'))
    merge_header_files(os.path.join(sys.argv[2], 'kernel'))
    print('=' * 80)
