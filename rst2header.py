from io import StringIO
import os
import re
import sys


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
    def __init__(self, name, description, offset):
        self.name = name.lower()
        self.description, self.description_ex = description
        self.offset = offset
        self.description_end = ''
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
        reg_str.write('^' * len(self.full_des) + '\n\n')
        reg_str.write('.. list-table::\n   :header-rows: 1\n\n')
        reg_str.write('   * - Bits\n     - Description\n     - Access\n'
                      '     - Reset\n     - Value\n')
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
                    raise Exception('bit conflict at {} bit {}'.
                                    format(self.full_des, reg_field.up))
                else:
                    raise Exception('bit conflict at {} bit {}:{}'.
                                    format(self.full_des, reg_field.up,
                                           reg_field.down))
            if reg_field.up < reg_field.down:
                raise Exception('bit conflict at {} bit {}:{}'.
                                format(self.full_des, reg_field.up,
                                       reg_field.down))
            cmp_down = reg_field.up + 1
        if cmp_down != 32:
            raise Exception('{} is not end with bit 31'.format(self.full_des))

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
    name_pattern = re.compile(r'^([A-Z][A-Z0-9_]+) \((.+?), '
                              r'0x([0-9A-F]{4}_[0-9A-F]{4})\)(?: (.+?))?$')
    section_pattern = re.compile(r'^(\^+)$')
    bit_pattern = re.compile(r'^ {3}\* - (\d+)(?::(\d+))?$')
    reserved_pattern = '     - Reserved'
    des0_pattern = re.compile(r'^ {5}- \*\*(\S+?)\*\* (.*)$')
    des1_pattern = re.compile(r'^ {7}(.+)$')
    access_pattern = re.compile(r'^ {5}- (RW|R/W|R|RO|W1P|W1C|W1P/R|' +
                                reserved_str + r')$')
    reset_pattern = re.compile(r'^ {5}- (0x[0-9A-F]+|' + reserved_str +
                               r')$')
    type_pattern = re.compile(r'^ {5}- (U|S|' + reserved_str + ')$')
    space_pattern = re.compile(r'[ \t]+$')
    start_str = ('.. raw:: latex\n\n'
                 '   \setregistertablestyle\n\n'
                 '.. tabularcolumns:: '
                 '|K{1cm}|p{10cm}|K{1.2cm}|K{1cm}|K{1cm}|\n\n')
    end_str = '.. tabularcolumns:: |l|l|l|l|l|l|l|l|l|l|\n'

    def __init__(self, rst_file, name):
        self.name = name
        self.regs = []
        with open(rst_file, 'r') as rf:
            rst_lines = rf.readlines()
        for i, line in enumerate(rst_lines, start=1):
            if Module.space_pattern.search(line):
                raise Exception('line {} - {}: has trailing white space'.
                                format(i, repr(line)))
            if line.find('\t') >= 0:
                raise Exception('line {} - {}: can not use tab for indenting'.
                                format(i, repr(line)))
            rst_lines[i - 1] = line.rstrip()
        if '\n'.join(rst_lines[0:6]) + '\n' != Module.start_str:
            raise Exception('rst file must start with:\n{}'.
                            format(Module.start_str))
        if rst_lines[-1] + '\n' != Module.end_str:
            raise Exception('rst file must end with:\n{}'.
                            format(Module.end_str))
        i = 0
        cmp_offset = 0
        while i < len(rst_lines):
            reg, i = Module.get_next_reg(rst_lines, i)
            if reg.offset < cmp_offset or reg.offset % 4:
                raise Exception('{} address offset error\n'.
                                format(reg.full_des))
            cmp_offset = reg.offset + 4
            self.regs.append(reg)

    def __str__(self):
        module_str = StringIO()
        module_str.write(Module.start_str)
        for reg in self.regs:
            module_str.write(str(reg))
        module_str.write(Module.end_str)
        return module_str.getvalue()

    @staticmethod
    def get_next_reg(rst_lines, i):
        name, description, offset, i = Module.get_next_reg_attr(rst_lines, i)
        if not name:
            return None, i
        reg = Register(name, description, offset)
        i = Module.append_all_reg_field(reg, rst_lines, i)
        return reg, i

    @staticmethod
    def get_register_end_des(rst_lines, begin, end):
        result = StringIO()
        i = begin
        last_line = len(rst_lines) - 1
        while i < min(end, last_line):
            if rst_lines[i]:
                if not rst_lines[i - 1]:
                    result.write('\n')
                else:
                    result.write(' ')
                result.write(rst_lines[i])
            i += 1
        return result.getvalue().lstrip()

    @staticmethod
    def append_all_reg_field(reg, rst_lines, i):
        bits = []
        while True:
            last_i = i
            bit, i = Module.get_next_reg_field(rst_lines, i)
            if bit is None:
                reg.description_end = Module.get_register_end_des(rst_lines,
                                                                  last_i, i)
                break
            else:
                bits.append(bit)
        reg.set_all_bits(bits)
        return i

    @staticmethod
    def get_next_reg_bit(rst_lines, i):
        while i < len(rst_lines):
            if Module.cur_line_to_attr(rst_lines, i)[0]:
                return None, i
            bit_match = Module.bit_pattern.match(rst_lines[i])
            i += 1
            if bit_match:
                up = bit_match.group(1)
                down = bit_match.group(2) if bit_match.group(2) else up
                return (int(up), int(down)), i
        return None, i

    @staticmethod
    def description_is_reserved(rst_lines, i):
        if rst_lines[i] == Module.reserved_pattern:
            return True
        else:
            return False

    @staticmethod
    def get_description(rst_lines, i):
        des0_match = Module.des0_pattern.match(rst_lines[i])
        if des0_match:
            name = des0_match.group(1)
            description = des0_match.group(2)
            i += 1
            while i < len(rst_lines):
                des1_match = Module.des1_pattern.match(rst_lines[i])
                if des1_match:
                    if not rst_lines[i - 1]:
                        description += '\n' + des1_match.group(1)
                    else:
                        description += ' ' + des1_match.group(1)
                    i += 1
                elif not rst_lines[i]:
                    i += 1
                else:
                    break
            return name, description, i
        else:
            raise Exception('line {}> {}: description format is error\n'
                            'correct string is \'Reserved\' or '
                            '\'**signal**[space]description\'\n'.
                            format(i + 1, repr(rst_lines[i])))

    @staticmethod
    def get_next_name_description(rst_lines, i):
        if Module.description_is_reserved(rst_lines, i):
            return reserved_str, 'Reserved', i + 1
        return Module.get_description(rst_lines, i)

    @staticmethod
    def cur_line_to_access(rst_lines, i):
        access_match = Module.access_pattern.match(rst_lines[i])
        if not access_match:
            raise Exception('line {}> {} can not find any access flag\n'
                            'correct flag is \'R/W|R|W1P|W1C|W1P/R|--\'\n'.
                            format(i + 1, repr(rst_lines[i])))
        return access_match.group(1)

    @staticmethod
    def cur_line_to_reset(rst_lines, i):
        reset_match = Module.reset_pattern.match(rst_lines[i])
        if not reset_match:
            raise Exception('line {}: reset value is error\n{}\n'
                            'correct eg: 0xA4. must be upper case\n'.
                            format(i + 1, rst_lines[i]))
        reset = reset_match.group(1)
        reset = ('0x{:X}'.format(int(reset, 16)) if reset != reserved_str
                 else reset)
        return reset

    @staticmethod
    def cur_line_to_type(rst_lines, i):
        type_match = Module.type_pattern.match(rst_lines[i])
        if not type_match:
            raise Exception('line {}: type flag incorrect\n{}\n'
                            'correct is \'U|S|--\''.
                            format(i + 1, rst_lines[i]))
        return type_match.group(1)

    @staticmethod
    def get_next_reg_field(rst_lines, i):
        bit, i = Module.get_next_reg_bit(rst_lines, i)
        if bit is None:
            return None, i
        name, description, i = Module.get_next_name_description(rst_lines, i)
        access = Module.cur_line_to_access(rst_lines, i)
        i += 1
        reset = Module.cur_line_to_reset(rst_lines, i)
        i += 1
        val_type = Module.cur_line_to_type(rst_lines, i)
        i += 1
        if name == reserved_str:
            reg_field = RegField(bit, reserved_str, 'Reserved', reserved_str,
                                 reserved_str, reserved_str)
        else:
            reg_field = RegField(bit, name, description, access, reset,
                                 val_type)
        return reg_field, i

    @staticmethod
    def cur_line_to_attr(rst_lines, i):
        name_match = Module.name_pattern.match(rst_lines[i])
        if name_match:
            i += 1
            section_match = Module.section_pattern.match(rst_lines[i])
            if (section_match and len(name_match.group(0)) <= len(
                    section_match.group(0))):
                i += 1
                name = name_match.group(1)
                offset = name_match.group(3)
                description = name_match.groups()[1:4:2]
                return name, description, int(offset.replace('_', ''), 16)
        elif Module.section_pattern.match(rst_lines[i]):
            raise Exception('line {} - {}: register name format error\n'
                            'correct is NAME[space](des,[space]0xXXXX_XXXX)'
                            '[space]des_ex\n'.
                            format(i, rst_lines[i - 1]))
        i += 1
        return '', ['', None], 0

    @staticmethod
    def get_next_reg_attr(rst_lines, i):
        while i < len(rst_lines):
            name, description, offset = Module.cur_line_to_attr(rst_lines, i)
            if name:
                return name, description, offset, i + 2
            else:
                i += 1
        return '', ['', None], 0, i

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
    for module in modules:
        input_file = os.path.join(modules_dir, module, 'registers.rst')
        user_file = os.path.join(user_dir, '{}_reg.h'.format(module))
        kernel_file = os.path.join(kernel_dir, '{}_reg.h'.format(module))
        print('convert {} to {}'.format(input_file, user_file))
        isp_module = Module(input_file, module)
        isp_module.generate_headers(user_file)
        print('convert {} to {}'.format(input_file, kernel_file))
        isp_module.generate_headers(kernel_file, user_space=False)
        # print(isp_module, end='')


def merge_header_files(headers_dir):
    with open(os.path.join(headers_dir, 'isp_reg.h'), 'w') as isp_header_file:
        modules = [name for name in os.listdir(headers_dir)
                   if name.endswith('.h') and name != 'isp_reg.h']
        for module in modules:
            isp_header_file.write('#include "{}"\n'.format(module))


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
